from datetime import datetime, date
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from config import settings, bot as tg_bot
from utils.FSM import AddWarmup
from utils.logger import logger
from utils.database import AccountRepository, ProxyRepository, decrypt_session


class CreationHelpers:
    @classmethod
    def is_admin(cls, tg_id: int) -> bool:
        return tg_id in settings.admins_list

    @classmethod
    async def proxy_rows(cls) -> list[tuple[str, str, str, str, int]]:
        from utils.database.db_engine import get_session_factory
        from utils.database.models import WarmupGroup as DBWarmupGroup
        from sqlalchemy import select

        try:
            async with get_session_factory()() as session:
                stmt = select(DBWarmupGroup.proxy_id).where(
                    DBWarmupGroup.proxy_id.is_not(None),
                    DBWarmupGroup.status.in_(["enabled", "paused"])
                )
                res = await session.execute(stmt)
                used_proxy_ids = set(res.scalars().all())
        except Exception as e:
            logger.error(f"Error fetching used proxies: {e}")
            used_proxy_ids = set()

        proxies = await ProxyRepository().get_all()
        free_proxies = [p for p in proxies if p.id not in used_proxy_ids]
        return [(p.id, p.name, p.proxy_type, p.host, p.port) for p in free_proxies]

    @classmethod
    async def edit_bot_msg(cls, state: FSMContext, text: str, reply_markup=None) -> None:
        data = await state.get_data()
        chat_id = data["bot_chat_id"]
        message_id = data["bot_message_id"]
        await tg_bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
        )

    @classmethod
    async def try_delete(cls, message: Message) -> None:
        try:
            await message.delete()
        except Exception:
            pass

    @classmethod
    async def build_preview_text(cls, data: dict) -> str:
        from utils.session_repo import SessionRepository
        selected: list[str] = list(data["selected"])
        acc_repo = AccountRepository()
        accounts = {a.id: a for a in await acc_repo.get_all()}
        chain_lines = []
        for i, acc_id in enumerate(selected):
            a = accounts.get(acc_id)
            chain_lines.append(
                f"{i + 1}. {SessionRepository.mask_phone(a.phone) if a else '?'}"
            )

        start_date = date.fromisoformat(data["start_date"])
        end_date = date.fromisoformat(data["end_date"])
        days = (end_date - start_date).days

        proxy_line = "без прокси ⚠️"
        proxy_id = data.get("proxy_id")
        if proxy_id:
            proxy = await ProxyRepository().get_by_id(proxy_id)
            if proxy:
                decrypted_user = decrypt_session(proxy.username) if proxy.username else None
                auth = f"{decrypted_user}:***@" if decrypted_user else ""
                proxy_line = f"{proxy.name} ({proxy.proxy_type}://{auth}{proxy.host}:{proxy.port})"

        return (
            f"📋 <b>Проверьте данные группы:</b>\n\n"
            f"📛 Название: <b>{data['name']}</b>\n"
            f"👥 Аккаунтов: <b>{len(selected)}</b>\n"
            f"📅 Период: <b>{start_date.strftime('%d.%m.%Y')}</b> — "
            f"<b>{end_date.strftime('%d.%m.%Y')}</b> ({days} дн.)\n"
            f"🌐 Прокси: <b>{proxy_line}</b>\n"
            f"🔁 Циклов на пару: {settings.WARMUP_CYCLES_PER_PAIR}\n"
            f"⏱ Интервал: {settings.WARMUP_MIN_INTERVAL_MIN}–"
            f"{settings.WARMUP_MAX_INTERVAL_MIN} мин\n"
            f"🕘 Окно дня: {settings.WARMUP_DAY_START_HOUR:02d}:00–"
            f"{settings.WARMUP_DAY_END_HOUR:02d}:00\n\n"
            f"<b>Цепочка:</b>\n" + "\n".join(chain_lines)
        )

    @classmethod
    async def show_confirm(cls, callback_or_state, state: FSMContext) -> None:
        from app.keyboards import warmup_confirm_kb
        data = await state.get_data()
        text = await cls.build_preview_text(data)
        await state.set_state(AddWarmup.waiting_confirm)
        if isinstance(callback_or_state, CallbackQuery):
            await callback_or_state.message.edit_text(
                text, reply_markup=warmup_confirm_kb())
        else:
            await cls.edit_bot_msg(state, text, reply_markup=warmup_confirm_kb())

    @classmethod
    async def proceed_to_proxy(cls, callback_or_state, state: FSMContext, end_date: date) -> None:
        from app.keyboards import warmup_end_date_kb, warmup_proxy_kb
        data = await state.get_data()
        start_date = date.fromisoformat(data["start_date"])
        if end_date < start_date:
            if isinstance(callback_or_state, CallbackQuery):
                await callback_or_state.answer(
                    "❌ Дата окончания раньше даты начала", show_alert=True)
            else:
                await cls.edit_bot_msg(
                    state,
                    "❌ Дата окончания раньше даты начала. Введите снова:\n\n"
                    "Введите <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
                    reply_markup=warmup_end_date_kb(start_date),
                )
            return

        await state.update_data(end_date=end_date.isoformat())
        await state.set_state(AddWarmup.waiting_proxy)

        free_proxies = await cls.proxy_rows()

        lines = ["⚠️ <b>Важно!</b> Пожалуйста, выберите прокси для группы.\n"]
        if not free_proxies:
            lines.append("❌ <b>Нет свободных прокси в базе данных!</b> Пожалуйста, добавьте новые прокси в главном меню.")
        else:
            lines.append("Один прокси — одна группа (до 6 аккаунтов).")

        text = "\n".join(lines)
        if isinstance(callback_or_state, CallbackQuery):
            await callback_or_state.message.edit_text(
                text, reply_markup=warmup_proxy_kb(free_proxies))
        else:
            await cls.edit_bot_msg(state, text, reply_markup=warmup_proxy_kb(free_proxies))
