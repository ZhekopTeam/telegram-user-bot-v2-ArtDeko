from datetime import datetime, timezone, date
from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from config import settings
from utils.logger import logger
from utils import SessionRepository, SheetsSync
from utils.database import (
    WarmupGroupRepository,
    ScheduledMessageRepository,
    AccountRepository,
    ProxyRepository,
)
from app.keyboards import (
    warmup_list_kb,
    warmup_detail_kb,
    warmup_queue_kb,
)

router_warmup_menu = Router(name="warmup_menu")


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admins_list


async def build_groups_view() -> list[tuple[str, str, str, str, int]]:
    repo = WarmupGroupRepository()
    groups = await repo.get_all()
    rows: list[tuple[str, str, str, str, int]] = []
    for g in groups:
        members = await repo.get_members(g.id)
        dates = f"{g.start_date.strftime('%d.%m')}–{g.end_date.strftime('%d.%m.%Y')}"
        rows.append((g.id, g.name, g.status, dates, len(members)))
    return rows


async def warmup_text() -> str:
    rows = await build_groups_view()
    if not rows:
        return "🔥 Групп прогрева нет."
    return f"🔥 <b>Группы прогрева</b> ({len(rows)}):"


async def render_detail(callback: CallbackQuery, group_id: str) -> None:
    g_repo = WarmupGroupRepository()
    msg_repo = ScheduledMessageRepository()
    acc_repo = AccountRepository()

    group = await g_repo.get_by_id(group_id)
    if not group:
        await callback.answer("Группа не найдена", show_alert=True)
        return

    members = await g_repo.get_members(group_id)
    accounts = {a.id: a for a in await acc_repo.get_all()}
    chain_lines = []
    for m in members:
        a = accounts.get(m.account_id)
        chain_lines.append(
            f"{m.position + 1}. {SessionRepository.mask_phone(a.phone) if a else '?'}"
        )

    stats = await msg_repo.count_by_status_for_group(group_id)
    stats_str = " | ".join(
        f"{k}: {v}" for k, v in sorted(stats.items())
    ) or "нет сообщений"

    last_planned = (
        group.last_planned_date.isoformat()
        if group.last_planned_date else "—"
    )

    proxy_line = "—"
    if group.proxy_id:
        proxy = await ProxyRepository().get_by_id(group.proxy_id)
        if proxy:
            proxy_line = f"{proxy.name} ({proxy.proxy_type})"

    text = (
        f"🆔 <code>{group.id[:8]}</code>\n"
        f"📛 <b>{group.name}</b>\n"
        f"📅 {group.start_date} — {group.end_date}\n"
        f"⚙️ Статус: <b>{group.status}</b>\n"
        f"🌐 Прокси: <b>{proxy_line}</b>\n"
        f"🔁 Циклов на пару: {group.cycles_per_pair}\n"
        f"⏱ Интервал: {group.min_interval_min}–{group.max_interval_min} мин\n"
        f"🕘 Окно дня: {group.day_start_hour:02d}:00–{group.day_end_hour:02d}:00\n"
        f"📊 {stats_str}\n"
        f"📌 Последнее планирование: {last_planned}\n\n"
        f"<b>Цепочка:</b>\n" + "\n".join(chain_lines)
    )
    await callback.message.edit_text(
        text, reply_markup=warmup_detail_kb(group.id, group.status))


@router_warmup_menu.callback_query(F.data == "menu:warmup")
async def cb_warmup_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    rows = await build_groups_view()
    await callback.message.edit_text(
        await warmup_text(),
        reply_markup=warmup_list_kb(rows),
    )
    await callback.answer()


@router_warmup_menu.callback_query(F.data.startswith("warmup:"))
async def cb_warmup_detail(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await render_detail(callback, group_id)
    await callback.answer()


@router_warmup_menu.callback_query(F.data.startswith("warmup_refresh:"))
async def cb_warmup_refresh(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    try:
        await render_detail(callback, group_id)
        await callback.answer("🔄 Обновлено")
    except Exception as e:
        if "message is not modified" in str(e):
            await callback.answer("✅ Данные актуальны")
        else:
            await callback.answer("Ошибка при обновлении")
            raise e


@router_warmup_menu.callback_query(F.data.startswith("warmup_pause:"))
async def cb_warmup_pause(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await WarmupGroupRepository().set_status(group_id, "paused")
    await ScheduledMessageRepository().cancel_pending_for_group(group_id)
    await SheetsSync.sync_warmup()
    await render_detail(callback, group_id)
    await callback.answer("⏸ Поставлено на паузу")


@router_warmup_menu.callback_query(F.data.startswith("warmup_resume:"))
async def cb_warmup_resume(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    group_repo = WarmupGroupRepository()
    await group_repo.set_status(group_id, "enabled")

    # Instantly trigger planning for today
    from accounts.warmup_planner import WarmupPlanner
    try:
        group = await group_repo.get_by_id(group_id)
        if group:
            planner = WarmupPlanner()
            await planner.plan_day(group, datetime.now().date())
    except Exception as e:
        logger.error(f"Failed to plan group {group_id} on resume: {e}")

    await SheetsSync.sync_warmup()
    await render_detail(callback, group_id)
    await callback.answer("▶️ Возобновлено")


@router_warmup_menu.callback_query(F.data.startswith("warmup_del:"))
async def cb_warmup_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await WarmupGroupRepository().delete(group_id)
    await callback.answer("🗑 Удалено")
    await SheetsSync.sync_warmup()
    rows = await build_groups_view()
    await callback.message.edit_text(
        await warmup_text(),
        reply_markup=warmup_list_kb(rows),
    )


@router_warmup_menu.callback_query(F.data.startswith("warmup_queue:"))
async def cb_warmup_queue(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    msg_repo = ScheduledMessageRepository()
    acc_repo = AccountRepository()
    upcoming = await msg_repo.get_upcoming_for_group(
        group_id, datetime.now(timezone.utc), limit=15)
    accounts = {a.id: a for a in await acc_repo.get_all()}

    if not upcoming:
        text = "📭 Ближайших сообщений нет."
    else:
        lines = []
        for m in upcoming:
            s = accounts.get(m.sender_id)
            r = accounts.get(m.receiver_id)
            ts = m.run_at.astimezone().strftime("%d.%m %H:%M")
            lines.append(
                f"• {ts} | {SessionRepository.mask_phone(s.phone) if s else '?'} → "
                f"{SessionRepository.mask_phone(r.phone) if r else '?'}"
            )
        text = "📋 <b>Ближайшие сообщения:</b>\n\n" + "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=warmup_queue_kb(group_id))
    await callback.answer()
