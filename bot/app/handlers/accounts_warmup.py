from datetime import datetime, timezone
from uuid import uuid4
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from config import settings
from utils.FSM import AddWarmup
from utils.logger import logger
from utils.session_repo import get_session_accounts, mask_phone
from utils.sheets_sync import sync_warmup
from utils.database import (
    WarmupGroupRepository,
    ScheduledMessageRepository,
    AccountRepository,
    WarmupGroup,
)
from accounts import WarmupPlanner
from app.keyboards import (
    warmup_list_kb,
    warmup_detail_kb,
    warmup_queue_kb,
    accounts_multipick_kb,
    warmup_cancel_kb,
)

router_warmup = Router(name="warmup")


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admins_list


async def _build_groups_view() -> list[tuple[str, str, str, str, int]]:
    repo = WarmupGroupRepository()
    groups = await repo.get_all()
    rows: list[tuple[str, str, str, str, int]] = []
    for g in groups:
        members = await repo.get_members(g.id)
        dates = f"{g.start_date.strftime('%d.%m')}–{g.end_date.strftime('%d.%m.%Y')}"
        rows.append((g.id, g.name, g.status, dates, len(members)))
    return rows


async def _warmup_text() -> str:
    rows = await _build_groups_view()
    if not rows:
        return "🔥 Групп прогрева нет."
    return f"🔥 <b>Группы прогрева</b> ({len(rows)}):"


@router_warmup.callback_query(F.data == "menu:warmup")
async def cb_warmup_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    rows = await _build_groups_view()
    await callback.message.edit_text(
        await _warmup_text(),
        reply_markup=warmup_list_kb(rows),
    )
    await callback.answer()


@router_warmup.callback_query(F.data.startswith("warmup:"))
async def cb_warmup_detail(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await _render_detail(callback, group_id)


async def _render_detail(callback: CallbackQuery, group_id: str) -> None:
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
            f"{m.position + 1}. {mask_phone(a.phone) if a else '?'}"
        )

    stats = await msg_repo.count_by_status_for_group(group_id)
    stats_str = " | ".join(
        f"{k}: {v}" for k, v in sorted(stats.items())
    ) or "нет сообщений"

    last_planned = (
        group.last_planned_date.isoformat()
        if group.last_planned_date else "—"
    )

    text = (
        f"🆔 <code>{group.id[:8]}</code>\n"
        f"📛 <b>{group.name}</b>\n"
        f"📅 {group.start_date} — {group.end_date}\n"
        f"⚙️ Статус: <b>{group.status}</b>\n"
        f"🔁 Циклов на пару: {group.cycles_per_pair}\n"
        f"⏱ Интервал: {group.min_interval_min}–{group.max_interval_min} мин\n"
        f"🕘 Окно дня: {group.day_start_hour:02d}:00–{group.day_end_hour:02d}:00\n"
        f"📊 {stats_str}\n"
        f"📌 Последнее планирование: {last_planned}\n\n"
        f"<b>Цепочка:</b>\n" + "\n".join(chain_lines)
    )
    await callback.message.edit_text(
        text, reply_markup=warmup_detail_kb(group.id, group.status))
    await callback.answer()


@router_warmup.callback_query(F.data.startswith("warmup_pause:"))
async def cb_warmup_pause(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await WarmupGroupRepository().set_status(group_id, "paused")
    await ScheduledMessageRepository().cancel_pending_for_group(group_id)
    await sync_warmup()
    await _render_detail(callback, group_id)


@router_warmup.callback_query(F.data.startswith("warmup_resume:"))
async def cb_warmup_resume(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await WarmupGroupRepository().set_status(group_id, "enabled")
    await sync_warmup()
    await _render_detail(callback, group_id)


@router_warmup.callback_query(F.data.startswith("warmup_del:"))
async def cb_warmup_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await WarmupGroupRepository().delete(group_id)
    await callback.answer("🗑 Удалено")
    await sync_warmup()
    rows = await _build_groups_view()
    await callback.message.edit_text(
        await _warmup_text(),
        reply_markup=warmup_list_kb(rows),
    )


@router_warmup.callback_query(F.data.startswith("warmup_queue:"))
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
                f"• {ts} | {mask_phone(s.phone) if s else '?'} → "
                f"{mask_phone(r.phone) if r else '?'}"
            )
        text = "📋 <b>Ближайшие сообщения:</b>\n\n" + "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=warmup_queue_kb(group_id))
    await callback.answer()


@router_warmup.callback_query(F.data == "warmup_add")
async def cb_warmup_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    accounts = await get_session_accounts()
    active = [a for a in accounts if a[2] == "active"]
    if len(active) < 2:
        await callback.answer(
            "⛔ Нужно минимум 2 активных аккаунта",
            show_alert=True,
        )
        return
    await state.set_state(AddWarmup.waiting_name)
    await callback.message.edit_text(
        "Введите <b>название</b> группы прогрева:",
        reply_markup=warmup_cancel_kb(),
    )
    await callback.answer()


@router_warmup.message(AddWarmup.waiting_name)
async def msg_group_name(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    name = message.text.strip()
    if not name or len(name) > 64:
        await message.answer(
            "❌ Название должно быть 1–64 символа.",
            reply_markup=warmup_cancel_kb(),
        )
        return
    await state.update_data(name=name, selected=[])
    accounts = await get_session_accounts()
    busy_ids = await WarmupGroupRepository().get_account_ids_in_active_groups()
    free_accounts = [a for a in accounts if a[0] not in busy_ids]
    if len([a for a in free_accounts if a[2] == "active"]) < 2:
        await state.clear()
        await message.answer(
            "⛔ Недостаточно свободных аккаунтов.\n"
            "Все активные аккаунты уже участвуют в прогреве.",
            reply_markup=warmup_cancel_kb(),
        )
        return
    await state.set_state(AddWarmup.waiting_accounts)
    await message.answer(
        "Выбирайте аккаунты <b>по порядку цепочки</b>. "
        "Минимум 2. Нажмите «✓ Готово», когда закончите:",
        reply_markup=accounts_multipick_kb(free_accounts, []),
    )


@router_warmup.callback_query(
    F.data.startswith("pick_acc:"),
    AddWarmup.waiting_accounts,
)
async def cb_pick_account(callback: CallbackQuery, state: FSMContext) -> None:
    account_id = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected: list[str] = list(data.get("selected", []))
    if account_id in selected:
        selected.remove(account_id)
    else:
        selected.append(account_id)
    await state.update_data(selected=selected)
    accounts = await get_session_accounts()
    busy_ids = await WarmupGroupRepository().get_account_ids_in_active_groups()
    free_accounts = [a for a in accounts if a[0] not in busy_ids]
    await callback.message.edit_reply_markup(
        reply_markup=accounts_multipick_kb(free_accounts, selected),
    )
    await callback.answer()


@router_warmup.callback_query(
    F.data == "warmup_accs_done",
    AddWarmup.waiting_accounts,
)
async def cb_accounts_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected: list[str] = list(data.get("selected", []))
    if len(selected) < 2:
        await callback.answer("Нужно минимум 2 аккаунта", show_alert=True)
        return
    await state.set_state(AddWarmup.waiting_start_date)
    await callback.message.edit_text(
        f"Выбрано аккаунтов: <b>{len(selected)}</b>\n\n"
        "Введите <b>дату начала</b> прогрева в формате <code>дд.мм.гггг</code>:",
        reply_markup=warmup_cancel_kb(),
    )
    await callback.answer()


@router_warmup.message(AddWarmup.waiting_start_date)
async def msg_start_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Пример: <code>24.05.2026</code>",
            reply_markup=warmup_cancel_kb(),
        )
        return
    await state.update_data(start_date=d.isoformat())
    await state.set_state(AddWarmup.waiting_end_date)
    await message.answer(
        "Теперь введите <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
        reply_markup=warmup_cancel_kb(),
    )


@router_warmup.message(AddWarmup.waiting_end_date)
async def msg_end_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Пример: <code>30.06.2026</code>",
            reply_markup=warmup_cancel_kb(),
        )
        return

    data = await state.get_data()
    start_date = datetime.fromisoformat(data["start_date"]).date()
    if end_date < start_date:
        await message.answer(
            "❌ Дата окончания раньше даты начала. Введите снова:",
            reply_markup=warmup_cancel_kb(),
        )
        return

    selected: list[str] = list(data["selected"])
    group = WarmupGroup(
        id=str(uuid4()),
        name=data["name"],
        start_date=start_date,
        end_date=end_date,
        status="enabled",
        cycles_per_pair=settings.WARMUP_CYCLES_PER_PAIR,
        min_interval_min=settings.WARMUP_MIN_INTERVAL_MIN,
        max_interval_min=settings.WARMUP_MAX_INTERVAL_MIN,
        day_start_hour=settings.WARMUP_DAY_START_HOUR,
        day_end_hour=settings.WARMUP_DAY_END_HOUR,
    )
    await WarmupGroupRepository().add(group, selected)
    logger.info(
        f"Warmup group {group.id} '{group.name}' added by {message.from_user.id}: "
        f"{len(selected)} accounts, {start_date}—{end_date}"
    )

    today = datetime.now().date()
    if start_date <= today <= end_date:
        try:
            await WarmupPlanner().plan_day(group, today)
        except Exception as e:
            logger.exception(f"Immediate plan failed for {group.id}: {e}")

    await state.clear()
    await sync_warmup()

    rows = await _build_groups_view()
    await message.answer(
        "✅ Группа прогрева создана!\n\n" + await _warmup_text(),
        reply_markup=warmup_list_kb(rows),
    )
