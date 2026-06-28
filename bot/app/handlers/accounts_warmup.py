from datetime import datetime, timezone, date, timedelta
from uuid import uuid4
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from config import settings, bot as tg_bot
from utils.FSM import AddWarmup
from utils.logger import logger
from utils.session_repo import get_session_accounts, mask_phone
from utils.sheets_sync import sync_warmup
from utils.database import (
    WarmupGroupRepository,
    ScheduledMessageRepository,
    AccountRepository,
    ProxyRepository,
    WarmupGroup,
)
from accounts import WarmupPlanner
from app.keyboards import (
    warmup_list_kb,
    warmup_detail_kb,
    warmup_queue_kb,
    accounts_multipick_kb,
    warmup_cancel_kb,
    warmup_start_date_kb,
    warmup_end_date_kb,
    warmup_proxy_kb,
    warmup_no_proxy_warning_kb,
    warmup_confirm_kb,
    warmup_edit_kb,
)

router_warmup = Router(name="warmup")


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admins_list


# ── helpers ───────────────────────────────────────────────────────

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


async def _proxy_rows() -> list[tuple[str, str, str, str, int]]:
    proxies = await ProxyRepository().get_all()
    return [(p.id, p.name, p.proxy_type, p.host, p.port) for p in proxies]


async def _edit_bot_msg(
    state: FSMContext, text: str, reply_markup=None,
) -> None:
    """Edit the stored bot message by ID (for text-input handlers)."""
    data = await state.get_data()
    chat_id = data["bot_chat_id"]
    message_id = data["bot_message_id"]
    await tg_bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=reply_markup,
    )


async def _edit_bot_msg_markup(state: FSMContext, reply_markup) -> None:
    """Edit only the reply_markup of the stored bot message."""
    data = await state.get_data()
    chat_id = data["bot_chat_id"]
    message_id = data["bot_message_id"]
    await tg_bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=reply_markup,
    )


async def _try_delete(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _build_preview_text(data: dict) -> str:
    """Build group preview from FSM state data (before DB save)."""
    selected: list[str] = list(data["selected"])
    acc_repo = AccountRepository()
    accounts = {a.id: a for a in await acc_repo.get_all()}
    chain_lines = []
    for i, acc_id in enumerate(selected):
        a = accounts.get(acc_id)
        chain_lines.append(
            f"{i + 1}. {mask_phone(a.phone) if a else '?'}"
        )

    start_date = date.fromisoformat(data["start_date"])
    end_date = date.fromisoformat(data["end_date"])
    days = (end_date - start_date).days

    proxy_line = "без прокси ⚠️"
    proxy_id = data.get("proxy_id")
    if proxy_id:
        proxy = await ProxyRepository().get_by_id(proxy_id)
        if proxy:
            auth = f"{proxy.username}:***@" if proxy.username else ""
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


async def _show_confirm(callback_or_state, state: FSMContext) -> None:
    """Show the confirmation screen. Works with callback or via bot_msg edit."""
    data = await state.get_data()
    text = await _build_preview_text(data)
    await state.set_state(AddWarmup.waiting_confirm)
    if isinstance(callback_or_state, CallbackQuery):
        await callback_or_state.message.edit_text(
            text, reply_markup=warmup_confirm_kb())
    else:
        await _edit_bot_msg(state, text, reply_markup=warmup_confirm_kb())


# ── warmup menu & detail (unchanged logic) ────────────────────────

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
    await callback.answer()


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


@router_warmup.callback_query(F.data.startswith("warmup_refresh:"))
async def cb_warmup_refresh(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    try:
        await _render_detail(callback, group_id)
        await callback.answer("🔄 Обновлено")
    except Exception as e:
        if "message is not modified" in str(e):
            await callback.answer("✅ Данные актуальны")
        else:
            await callback.answer("Ошибка при обновлении")
            raise e


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
    await callback.answer("⏸ Поставлено на паузу")


@router_warmup.callback_query(F.data.startswith("warmup_resume:"))
async def cb_warmup_resume(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await WarmupGroupRepository().set_status(group_id, "enabled")
    await sync_warmup()
    await _render_detail(callback, group_id)
    await callback.answer("▶️ Возобновлено")


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


# ══════════════════════════════════════════════════════════════════
#  WARMUP GROUP CREATION FLOW
#  All steps edit ONE bot message stored as bot_message_id in state.
# ══════════════════════════════════════════════════════════════════

# ── Step 1: start → ask name ──────────────────────────────────────

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
    await state.update_data(
        bot_message_id=callback.message.message_id,
        bot_chat_id=callback.message.chat.id,
    )
    await callback.answer()


# ── Step 2: name → account picker ─────────────────────────────────

@router_warmup.message(AddWarmup.waiting_name)
async def msg_group_name(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    name = message.text.strip()
    await _try_delete(message)
    if not name or len(name) > 64:
        await _edit_bot_msg(
            state,
            "❌ Название должно быть 1–64 символа.\n\n"
            "Введите <b>название</b> группы прогрева:",
            reply_markup=warmup_cancel_kb(),
        )
        return
    await state.update_data(name=name, selected=[])
    accounts = await get_session_accounts()
    busy_ids = await WarmupGroupRepository().get_account_ids_in_active_groups()
    free_accounts = [a for a in accounts if a[0] not in busy_ids]
    if len([a for a in free_accounts if a[2] == "active"]) < 2:
        data = await state.get_data()
        chat_id = data["bot_chat_id"]
        message_id = data["bot_message_id"]
        await state.clear()
        await tg_bot.edit_message_text(
            text="⛔ Недостаточно свободных аккаунтов.\n"
            "Все активные аккаунты уже участвуют в прогреве.",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=warmup_cancel_kb(),
        )
        return
    await state.set_state(AddWarmup.waiting_accounts)
    await _edit_bot_msg(
        state,
        "Выбирайте аккаунты <b>по порядку цепочки</b>. "
        "Минимум 2, максимум 6. Нажмите «✓ Готово», когда закончите:",
        reply_markup=accounts_multipick_kb(free_accounts, []),
    )


# ── Step 3: account picking ──────────────────────────────────────

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
        if len(selected) >= 6:
            await callback.answer("Максимум 6 аккаунтов", show_alert=True)
            return
        selected.append(account_id)
    await state.update_data(selected=selected)
    accounts = await get_session_accounts()
    busy_ids = await WarmupGroupRepository().get_account_ids_in_active_groups()
    free_accounts = [a for a in accounts if a[0] not in busy_ids]
    await callback.message.edit_reply_markup(
        reply_markup=accounts_multipick_kb(free_accounts, selected),
    )
    await callback.answer()


# ── Step 4: accounts done → ask start date ────────────────────────

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
        reply_markup=warmup_start_date_kb(),
    )
    await callback.answer()


# ── Step 5a: start date via button ────────────────────────────────

@router_warmup.callback_query(
    F.data.startswith("warmup_start_date:"),
    AddWarmup.waiting_start_date,
)
async def cb_start_date_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    date_val = callback.data.split(":", 1)[1]
    if date_val == "other":
        await callback.message.edit_reply_markup(reply_markup=warmup_cancel_kb())
        await callback.answer()
        return
    try:
        d = datetime.strptime(date_val, "%d.%m.%Y").date()
    except ValueError:
        await callback.answer("Ошибка формата даты", show_alert=True)
        return
    await state.update_data(start_date=d.isoformat())
    await state.set_state(AddWarmup.waiting_end_date)
    await callback.message.edit_text(
        "Теперь введите <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
        reply_markup=warmup_end_date_kb(d),
    )
    await callback.answer()


# ── Step 5b: start date via text ──────────────────────────────────

@router_warmup.message(AddWarmup.waiting_start_date)
async def msg_start_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await _try_delete(message)
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await _edit_bot_msg(
            state,
            "❌ Неверный формат. Пример: <code>24.05.2026</code>\n\n"
            "Введите <b>дату начала</b> прогрева в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_start_date_kb(),
        )
        return
    await state.update_data(start_date=d.isoformat())
    await state.set_state(AddWarmup.waiting_end_date)
    await _edit_bot_msg(
        state,
        "Теперь введите <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
        reply_markup=warmup_end_date_kb(d),
    )


# ── Step 6a: end date via button → proxy ──────────────────────────

async def _proceed_to_proxy(callback_or_state, state: FSMContext, end_date: date) -> None:
    """Common logic after end_date is accepted: go to proxy selection."""
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    if end_date < start_date:
        if isinstance(callback_or_state, CallbackQuery):
            await callback_or_state.answer(
                "❌ Дата окончания раньше даты начала", show_alert=True)
        else:
            await _edit_bot_msg(
                state,
                "❌ Дата окончания раньше даты начала. Введите снова:\n\n"
                "Введите <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
                reply_markup=warmup_end_date_kb(start_date),
            )
        return

    await state.update_data(end_date=end_date.isoformat())
    await state.set_state(AddWarmup.waiting_proxy)

    proxies = await _proxy_rows()
    text = (
        "⚠️ <b>Важно!</b> Пожалуйста, выберите прокси для группы.\n\n"
        "Один прокси — одна группа (до 6 аккаунтов)."
    )
    if isinstance(callback_or_state, CallbackQuery):
        await callback_or_state.message.edit_text(
            text, reply_markup=warmup_proxy_kb(proxies))
    else:
        await _edit_bot_msg(state, text, reply_markup=warmup_proxy_kb(proxies))


@router_warmup.callback_query(
    F.data.startswith("warmup_end_date:"),
    AddWarmup.waiting_end_date,
)
async def cb_end_date_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    date_val = callback.data.split(":", 1)[1]
    if date_val == "other":
        await callback.message.edit_reply_markup(reply_markup=warmup_cancel_kb())
        await callback.answer()
        return
    try:
        end_date = datetime.strptime(date_val, "%d.%m.%Y").date()
    except ValueError:
        await callback.answer("Ошибка формата даты", show_alert=True)
        return
    await _proceed_to_proxy(callback, state, end_date)
    await callback.answer()


# ── Step 6b: end date via text ────────────────────────────────────

@router_warmup.message(AddWarmup.waiting_end_date)
async def msg_end_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await _try_delete(message)
    try:
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        data = await state.get_data()
        start_date = date.fromisoformat(data["start_date"])
        await _edit_bot_msg(
            state,
            "❌ Неверный формат. Пример: <code>30.06.2026</code>\n\n"
            "Введите <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_end_date_kb(start_date),
        )
        return
    await _proceed_to_proxy(message, state, end_date)


# ── Step 7: proxy selection ───────────────────────────────────────

@router_warmup.callback_query(
    F.data.startswith("warmup_pick_proxy:"),
    AddWarmup.waiting_proxy,
)
async def cb_proxy_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    proxy_id = callback.data.split(":", 1)[1]
    await state.update_data(proxy_id=proxy_id)
    await _show_confirm(callback, state)
    await callback.answer()


@router_warmup.callback_query(
    F.data == "warmup_no_proxy",
    AddWarmup.waiting_proxy,
)
async def cb_no_proxy(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.message.edit_text(
        "⚠️ <b>Без прокси риск бана аккаунтов значительно выше!</b>\n\n"
        "Рекомендуется использовать прокси для безопасного прогрева.",
        reply_markup=warmup_no_proxy_warning_kb(),
    )
    await callback.answer()


@router_warmup.callback_query(
    F.data == "warmup_select_proxy_back",
    AddWarmup.waiting_proxy,
)
async def cb_select_proxy_back(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    proxies = await _proxy_rows()
    await callback.message.edit_text(
        "⚠️ <b>Важно!</b> Пожалуйста, выберите прокси для группы.\n\n"
        "Один прокси — одна группа (до 6 аккаунтов).",
        reply_markup=warmup_proxy_kb(proxies),
    )
    await callback.answer()


@router_warmup.callback_query(
    F.data == "warmup_no_proxy_confirm",
    AddWarmup.waiting_proxy,
)
async def cb_no_proxy_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(proxy_id=None)
    await _show_confirm(callback, state)
    await callback.answer()


# ── Step 8: confirmation screen ───────────────────────────────────

@router_warmup.callback_query(
    F.data == "warmup_confirm_ok",
    AddWarmup.waiting_confirm,
)
async def cb_confirm_ok(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    end_date = date.fromisoformat(data["end_date"])
    selected: list[str] = list(data["selected"])
    proxy_id = data.get("proxy_id")

    group = WarmupGroup(
        id=str(uuid4()),
        name=data["name"],
        proxy_id=proxy_id,
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
        f"Warmup group {group.id} '{group.name}' added by {callback.from_user.id}: "
        f"{len(selected)} accounts, {start_date}—{end_date}, proxy={proxy_id}"
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
    await callback.message.edit_text(
        "✅ Группа прогрева создана!\n\n" + await _warmup_text(),
        reply_markup=warmup_list_kb(rows),
    )
    await callback.answer()


# ── Step 8b: edit mode ────────────────────────────────────────────

@router_warmup.callback_query(
    F.data == "warmup_confirm_edit",
    AddWarmup.waiting_confirm,
)
async def cb_confirm_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddWarmup.waiting_edit)
    await callback.message.edit_reply_markup(reply_markup=warmup_edit_kb())
    await callback.answer()


@router_warmup.callback_query(
    F.data == "warmup_edit_back",
    AddWarmup.waiting_edit,
)
async def cb_edit_back(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddWarmup.waiting_confirm)
    await callback.message.edit_reply_markup(reply_markup=warmup_confirm_kb())
    await callback.answer()


# ── Edit: start date ──────────────────────────────────────────────

@router_warmup.callback_query(
    F.data == "warmup_edit_start",
    AddWarmup.waiting_edit,
)
async def cb_edit_start_date(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddWarmup.waiting_edit_start_date)
    await callback.message.edit_text(
        "Введите новую <b>дату начала</b> в формате <code>дд.мм.гггг</code>:",
        reply_markup=warmup_start_date_kb(),
    )
    await callback.answer()


@router_warmup.callback_query(
    F.data.startswith("warmup_start_date:"),
    AddWarmup.waiting_edit_start_date,
)
async def cb_edit_start_date_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    date_val = callback.data.split(":", 1)[1]
    if date_val == "other":
        await callback.message.edit_reply_markup(reply_markup=warmup_cancel_kb())
        await callback.answer()
        return
    try:
        d = datetime.strptime(date_val, "%d.%m.%Y").date()
    except ValueError:
        await callback.answer("Ошибка формата даты", show_alert=True)
        return
    await state.update_data(start_date=d.isoformat())
    await _show_confirm(callback, state)
    await callback.answer()


@router_warmup.message(AddWarmup.waiting_edit_start_date)
async def msg_edit_start_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await _try_delete(message)
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await _edit_bot_msg(
            state,
            "❌ Неверный формат. Пример: <code>24.05.2026</code>\n\n"
            "Введите новую <b>дату начала</b> в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_start_date_kb(),
        )
        return
    await state.update_data(start_date=d.isoformat())
    await _show_confirm(None, state)


# ── Edit: end date ────────────────────────────────────────────────

@router_warmup.callback_query(
    F.data == "warmup_edit_end",
    AddWarmup.waiting_edit,
)
async def cb_edit_end_date(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    await state.set_state(AddWarmup.waiting_edit_end_date)
    await callback.message.edit_text(
        "Введите новую <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
        reply_markup=warmup_end_date_kb(start_date),
    )
    await callback.answer()


@router_warmup.callback_query(
    F.data.startswith("warmup_end_date:"),
    AddWarmup.waiting_edit_end_date,
)
async def cb_edit_end_date_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    date_val = callback.data.split(":", 1)[1]
    if date_val == "other":
        await callback.message.edit_reply_markup(reply_markup=warmup_cancel_kb())
        await callback.answer()
        return
    try:
        end_date = datetime.strptime(date_val, "%d.%m.%Y").date()
    except ValueError:
        await callback.answer("Ошибка формата даты", show_alert=True)
        return
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    if end_date < start_date:
        await callback.answer("❌ Дата окончания раньше даты начала", show_alert=True)
        return
    await state.update_data(end_date=end_date.isoformat())
    await _show_confirm(callback, state)
    await callback.answer()


@router_warmup.message(AddWarmup.waiting_edit_end_date)
async def msg_edit_end_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await _try_delete(message)
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    try:
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await _edit_bot_msg(
            state,
            "❌ Неверный формат. Пример: <code>30.06.2026</code>\n\n"
            "Введите новую <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_end_date_kb(start_date),
        )
        return
    if end_date < start_date:
        await _edit_bot_msg(
            state,
            "❌ Дата окончания раньше даты начала. Введите снова:\n\n"
            "Введите новую <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_end_date_kb(start_date),
        )
        return
    await state.update_data(end_date=end_date.isoformat())
    await _show_confirm(None, state)


# ── Edit: days count ──────────────────────────────────────────────

@router_warmup.callback_query(
    F.data == "warmup_edit_days",
    AddWarmup.waiting_edit,
)
async def cb_edit_days(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddWarmup.waiting_edit_days)
    await callback.message.edit_text(
        "Введите <b>количество дней</b> прогрева (число).\n"
        "Дата окончания будет рассчитана от даты начала.",
        reply_markup=warmup_cancel_kb(),
    )
    await callback.answer()


@router_warmup.message(AddWarmup.waiting_edit_days)
async def msg_edit_days(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await _try_delete(message)
    try:
        days = int(message.text.strip())
        if days < 1:
            raise ValueError
    except ValueError:
        await _edit_bot_msg(
            state,
            "❌ Введите положительное целое число.\n\n"
            "Введите <b>количество дней</b> прогрева:",
            reply_markup=warmup_cancel_kb(),
        )
        return
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    end_date = start_date + timedelta(days=days)
    await state.update_data(end_date=end_date.isoformat())
    await _show_confirm(None, state)
