from datetime import datetime, date
from uuid import uuid4
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from config import settings, bot as tg_bot
from utils.FSM import AddWarmup
from utils.logger import logger
from utils import SessionRepository, SheetsSync, CreationHelpers
from utils.database import (
    WarmupGroupRepository,
    WarmupGroup,
)
from accounts import WarmupPlanner
from app.keyboards import (
    warmup_list_kb,
    accounts_multipick_kb,
    warmup_cancel_kb,
    warmup_start_date_kb,
    warmup_end_date_kb,
)
from .warmup_menu import build_groups_view, warmup_text

router_warmup_perfect = Router(name="warmup_perfect")


@router_warmup_perfect.callback_query(F.data == "warmup_add")
async def cb_warmup_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    accounts = await SessionRepository.get_session_accounts()
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


@router_warmup_perfect.message(AddWarmup.waiting_name)
async def msg_group_name(message: Message, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(message.from_user.id):
        return
    name = message.text.strip()
    await CreationHelpers.try_delete(message)
    if not name or len(name) > 64:
        await CreationHelpers.edit_bot_msg(
            state,
            "❌ Название должно быть 1–64 символа.\n\n"
            "Введите <b>название</b> группы прогрева:",
            reply_markup=warmup_cancel_kb(),
        )
        return
    await state.update_data(name=name, selected=[])
    accounts = await SessionRepository.get_session_accounts()
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
    await CreationHelpers.edit_bot_msg(
        state,
        "Выбирайте аккаунты <b>по порядку цепочки</b>. "
        "Минимум 2, максимум 6. Нажмите «✓ Готово», когда закончите:",
        reply_markup=accounts_multipick_kb(free_accounts, []),
    )


@router_warmup_perfect.callback_query(
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
    accounts = await SessionRepository.get_session_accounts()
    busy_ids = await WarmupGroupRepository().get_account_ids_in_active_groups()
    free_accounts = [a for a in accounts if a[0] not in busy_ids]
    await callback.message.edit_reply_markup(
        reply_markup=accounts_multipick_kb(free_accounts, selected),
    )
    await callback.answer()


@router_warmup_perfect.callback_query(
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


@router_warmup_perfect.callback_query(
    F.data.startswith("warmup_start_date:"),
    AddWarmup.waiting_start_date,
)
async def cb_start_date_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
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


@router_warmup_perfect.callback_query(
    F.data.startswith("warmup_end_date:"),
    AddWarmup.waiting_end_date,
)
async def cb_end_date_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
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
    await CreationHelpers.proceed_to_proxy(callback, state, end_date)
    await callback.answer()


@router_warmup_perfect.callback_query(
    F.data.startswith("warmup_pick_proxy:"),
    AddWarmup.waiting_proxy,
)
async def cb_proxy_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    proxy_id = callback.data.split(":", 1)[1]
    await state.update_data(proxy_id=proxy_id)
    await CreationHelpers.show_confirm(callback, state)
    await callback.answer()


@router_warmup_perfect.callback_query(
    F.data == "warmup_confirm_ok",
    AddWarmup.waiting_confirm,
)
async def cb_confirm_ok(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
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
    await SheetsSync.sync_warmup()

    rows = await build_groups_view()
    await callback.message.edit_text(
        "✅ Группа прогрева создана!\n\n" + await warmup_text(),
        reply_markup=warmup_list_kb(rows),
    )
    await callback.answer()
