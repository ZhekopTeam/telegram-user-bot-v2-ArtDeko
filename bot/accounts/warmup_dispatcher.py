import asyncio
import json
import random
import string
from pathlib import Path
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from pyrogram.errors import (
    AuthKeyUnregistered,
    UserDeactivated,
    SessionRevoked,
    FloodWait,
)
from pyrogram.raw.functions.contacts import ImportContacts
from pyrogram.raw.types import InputPhoneContact

from config import settings
from utils.logger import logger
from utils.database import (
    AccountRepository,
    ScheduledMessageRepository,
    ScheduledMessage,
    WarmupGroupRepository,
)
from utils import BotNotifications
from accounts.client_manager import ClientManager
from accounts.warmup_planner import WarmupPlanner


_FATAL_SESSION_ERRORS = (AuthKeyUnregistered, UserDeactivated, SessionRevoked)
_MAX_ATTEMPTS = 3

_SENTENCES: list[str] = []


def _load_sentences() -> None:
    global _SENTENCES
    path = Path(settings.DATABASE_PATH).parent / "sentences_list.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _SENTENCES = data.get("sentences", [])
        logger.info(f"Loaded {len(_SENTENCES)} warmup sentences")
    except Exception as e:
        logger.warning(
            f"Could not load sentences_list.json: {e}. Fallback to random text.")


def _random_text() -> str:
    if _SENTENCES:
        count = random.randint(2, 3)
        return " ".join(random.sample(_SENTENCES, min(count, len(_SENTENCES))))
    length = random.randint(4, 12)
    return "".join(random.choice(string.ascii_letters + " ") for _ in range(length)).strip() or "hi"


class WarmupDispatcher:
    """Тикер очереди прогрева: каждые N секунд забирает due-сообщения
    из БД и отправляет их через ClientManager. Переживает рестарты,
    потому что вся очередь — в SQLite, а не в asyncio.sleep."""

    def __init__(self, bot: Bot, client_manager: ClientManager):
        self._bot = bot
        self._cm = client_manager
        self._messages = ScheduledMessageRepository()
        self._accounts = AccountRepository()
        self._groups = WarmupGroupRepository()
        self._planner = WarmupPlanner()
        self._scheduler = AsyncIOScheduler()
        self._tick_lock = asyncio.Lock()

    def start(self) -> None:
        _load_sentences()
        self._scheduler.add_job(
            self._daily_plan,
            CronTrigger(
                hour=settings.WARMUP_PLAN_HOUR,
                minute=settings.WARMUP_PLAN_MINUTE,
            ),
            id="warmup_daily_plan",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        self._scheduler.add_job(
            self._tick,
            IntervalTrigger(seconds=settings.WARMUP_DISPATCH_INTERVAL_SEC),
            id="warmup_dispatch_tick",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._catch_up_plan_on_start,
            "date",
            id="warmup_catch_up_plan",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            f"WarmupDispatcher armed: plan at {settings.WARMUP_PLAN_HOUR:02d}:"
            f"{settings.WARMUP_PLAN_MINUTE:02d}, "
            f"tick every {settings.WARMUP_DISPATCH_INTERVAL_SEC}s"
        )

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def _catch_up_plan_on_start(self) -> None:
        try:
            today = datetime.now().date()
            planned = await self._planner.plan_today_for_all(today)
            if planned:
                logger.info(f"Catch-up planning on start: {planned} groups")
        except Exception as e:
            logger.exception(f"Catch-up planning failed: {e}")

    async def _daily_plan(self) -> None:
        try:
            today = datetime.now().date()
            planned = await self._planner.plan_today_for_all(today)
            logger.info(
                f"Daily planning: {planned} groups planned for {today}")
            deleted = await self._messages.delete_old(older_than_days=7)
            if deleted:
                logger.info(
                    f"Cleanup: removed {deleted} old scheduled messages")
        except Exception as e:
            logger.exception(f"Daily planning failed: {e}")

    async def _tick(self) -> None:
        if self._tick_lock.locked():
            return
        async with self._tick_lock:
            try:
                now = datetime.now(timezone.utc)
                due = await self._messages.get_due(now, limit=50)
                for msg in due:
                    await self._dispatch_one(msg)
            except Exception as e:
                logger.exception(f"Dispatcher tick failed: {e}")

    async def _dispatch_one(self, msg: ScheduledMessage) -> None:
        group = await self._groups.get_by_id(msg.group_id)
        if group is not None:
            now_local = datetime.now()
            msg_date_local = msg.run_at.astimezone().date()
            if msg_date_local < now_local.date():
                await self._messages.mark_failed(msg.id, "day window expired")
                logger.debug(
                    f"Cancelled stale msg {msg.id[:8]} (scheduled for {msg_date_local})")
                return
            day_end_today = now_local.replace(
                hour=group.day_end_hour, minute=0, second=0, microsecond=0)
            if now_local > day_end_today:
                await self._messages.mark_failed(msg.id, "day window expired")
                logger.debug(
                    f"Cancelled msg {msg.id[:8]}: past day_end_hour ({group.day_end_hour}:00)")
                return

        sender = await self._accounts.get_by_id(msg.sender_id)
        receiver = await self._accounts.get_by_id(msg.receiver_id)

        if not sender or not receiver:
            await self._messages.mark_failed(msg.id, "account not found")
            return

        if sender.status != "active" or receiver.status != "active":
            await self._messages.mark_failed(
                msg.id,
                f"inactive: {sender.phone}={sender.status}, "
                f"{receiver.phone}={receiver.status}",
            )
            return

        bot_client = await self._cm.get_or_start(sender.id)
        if bot_client is None:
            await self._reschedule_or_fail(
                msg, f"sender client {sender.phone} unavailable")
            return

        try:
            await bot_client.client.invoke(
                ImportContacts(contacts=[
                    InputPhoneContact(
                        client_id=0,
                        phone=receiver.phone,
                        first_name="u",
                        last_name="",
                    )
                ])
            )
            await bot_client.client.send_message(receiver.tg_id, _random_text())
            receiver_client = await self._cm.get_or_start(receiver.id)
            if receiver_client is not None:
                try:
                    await receiver_client.client.read_chat_history(sender.tg_id)
                except Exception as e:
                    logger.debug(
                        f"read_chat_history failed for {receiver.phone}: {e}")
        except FloodWait as e:
            wait_sec = getattr(e, "value", 60) or 60
            new_run_at = datetime.now(timezone.utc) + \
                timedelta(seconds=wait_sec + 5)
            await self._messages.reschedule_retry(
                msg.id, new_run_at, f"FloodWait {wait_sec}s")
            logger.warning(
                f"FloodWait {wait_sec}s for {sender.phone}, rescheduled msg {msg.id}")
            return
        except _FATAL_SESSION_ERRORS as e:
            await BotNotifications.notify_session_revoked(
                self._bot, sender.tg_id, sender.phone, type(e).__name__)
            await self._cm.stop(sender.id)
            await self._messages.mark_failed(msg.id, f"session: {type(e).__name__}")
            return
        except Exception as e:
            await self._reschedule_or_fail(
                msg, f"send error: {type(e).__name__}: {e}")
            return

        await self._messages.mark_sent(msg.id, datetime.now(timezone.utc))
        sender_ip = bot_client.ip if bot_client else "unknown"
        receiver_ip = receiver_client.ip if receiver_client else "unknown"
        logger.info(
            f"Group: {group.name}:Sent msg {msg.id}: {sender.phone} [{sender_ip}] → {receiver.phone} [{receiver_ip}] "
            f"(pair={msg.pair_index} cycle={msg.cycle_index} dir={msg.direction})"
        )

    async def _reschedule_or_fail(self, msg: ScheduledMessage, error: str) -> None:
        if msg.attempts + 1 >= _MAX_ATTEMPTS:
            await self._messages.mark_failed(msg.id, error)
            await BotNotifications.notify_admins(
                self._bot,
                "🚨 <b>Сообщение прогрева провалено</b>\n"
                f"🆔 <code>{msg.id[:8]}</code>\n"
                f"💬 {error}",
            )
            return
        backoff_min = 5 * (2 ** msg.attempts)
        new_run_at = datetime.now(timezone.utc) + \
            timedelta(minutes=backoff_min)
        await self._messages.reschedule_retry(msg.id, new_run_at, error)
        logger.warning(
            f"Rescheduled msg {msg.id} in {backoff_min}m (attempt {msg.attempts + 1}): {error}"
        )
