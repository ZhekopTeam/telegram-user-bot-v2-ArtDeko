from datetime import datetime, date, timedelta
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from utils.FSM import AddWarmup
from utils import CreationHelpers
from app.keyboards import (
    warmup_proxy_kb,
    warmup_no_proxy_warning_kb,
    warmup_confirm_kb,
    warmup_edit_kb,
    warmup_start_date_kb,
    warmup_end_date_kb,
    warmup_cancel_kb,
)

router_warmup_exceptions = Router(name="warmup_exceptions")


@router_warmup_exceptions.callback_query(
    F.data == "warmup_no_proxy",
    AddWarmup.waiting_proxy,
)
async def cb_no_proxy(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.message.edit_text(
        "⚠️ <b>Без прокси риск бана аккаунтов значительно выше!</b>\n\n"
        "Рекомендуется использовать прокси для безопасного прогрева.",
        reply_markup=warmup_no_proxy_warning_kb(),
    )
    await callback.answer()


@router_warmup_exceptions.callback_query(
    F.data == "warmup_select_proxy_back",
    AddWarmup.waiting_proxy,
)
async def cb_select_proxy_back(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    free_proxies = await CreationHelpers.proxy_rows()

    lines = ["⚠️ <b>Важно!</b> Пожалуйста, выберите прокси для группы.\n"]
    if not free_proxies:
        lines.append("❌ <b>Нет свободных прокси в базе данных!</b> Пожалуйста, добавьте новые прокси в главном меню.")
    else:
        lines.append("Один прокси — одна группа (до 6 аккаунтов).")

    text = "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=warmup_proxy_kb(free_proxies),
    )
    await callback.answer()


@router_warmup_exceptions.callback_query(
    F.data == "warmup_no_proxy_confirm",
    AddWarmup.waiting_proxy,
)
async def cb_no_proxy_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(proxy_id=None)
    await CreationHelpers.show_confirm(callback, state)
    await callback.answer()


@router_warmup_exceptions.callback_query(
    F.data == "warmup_confirm_edit",
    AddWarmup.waiting_confirm,
)
async def cb_confirm_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddWarmup.waiting_edit)
    await callback.message.edit_reply_markup(reply_markup=warmup_edit_kb())
    await callback.answer()


@router_warmup_exceptions.callback_query(
    F.data == "warmup_edit_back",
    AddWarmup.waiting_edit,
)
async def cb_edit_back(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddWarmup.waiting_confirm)
    await callback.message.edit_reply_markup(reply_markup=warmup_confirm_kb())
    await callback.answer()


@router_warmup_exceptions.callback_query(
    F.data == "warmup_edit_start",
    AddWarmup.waiting_edit,
)
async def cb_edit_start_date(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddWarmup.waiting_edit_start_date)
    await callback.message.edit_text(
        "Введите новую <b>дату начала</b> в формате <code>дд.мм.гггг</code>:",
        reply_markup=warmup_start_date_kb(),
    )
    await callback.answer()


@router_warmup_exceptions.callback_query(
    F.data.startswith("warmup_start_date:"),
    AddWarmup.waiting_edit_start_date,
)
async def cb_edit_start_date_pick(callback: CallbackQuery, state: FSMContext) -> None:
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
    await CreationHelpers.show_confirm(callback, state)
    await callback.answer()


@router_warmup_exceptions.message(AddWarmup.waiting_edit_start_date)
async def msg_edit_start_date(message: Message, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(message.from_user.id):
        return
    await CreationHelpers.try_delete(message)
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await CreationHelpers.edit_bot_msg(
            state,
            "❌ Неверный формат. Пример: <code>24.05.2026</code>\n\n"
            "Введите новую <b>дату начала</b> в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_start_date_kb(),
        )
        return
    await state.update_data(start_date=d.isoformat())
    await CreationHelpers.show_confirm(None, state)


@router_warmup_exceptions.callback_query(
    F.data == "warmup_edit_end",
    AddWarmup.waiting_edit,
)
async def cb_edit_end_date(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
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


@router_warmup_exceptions.callback_query(
    F.data.startswith("warmup_end_date:"),
    AddWarmup.waiting_edit_end_date,
)
async def cb_edit_end_date_pick(callback: CallbackQuery, state: FSMContext) -> None:
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
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    if end_date < start_date:
        await callback.answer("❌ Дата окончания раньше даты начала", show_alert=True)
        return
    await state.update_data(end_date=end_date.isoformat())
    await CreationHelpers.show_confirm(callback, state)
    await callback.answer()


@router_warmup_exceptions.message(AddWarmup.waiting_edit_end_date)
async def msg_edit_end_date(message: Message, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(message.from_user.id):
        return
    await CreationHelpers.try_delete(message)
    data = await state.get_data()
    start_date = date.fromisoformat(data["start_date"])
    try:
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await CreationHelpers.edit_bot_msg(
            state,
            "❌ Неверный формат. Пример: <code>30.06.2026</code>\n\n"
            "Введите новую <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_end_date_kb(start_date),
        )
        return
    if end_date < start_date:
        await CreationHelpers.edit_bot_msg(
            state,
            "❌ Дата окончания раньше даты начала. Введите снова:\n\n"
            "Введите новую <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_end_date_kb(start_date),
        )
        return
    await state.update_data(end_date=end_date.isoformat())
    await CreationHelpers.show_confirm(None, state)


@router_warmup_exceptions.callback_query(
    F.data == "warmup_edit_days",
    AddWarmup.waiting_edit,
)
async def cb_edit_days(callback: CallbackQuery, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddWarmup.waiting_edit_days)
    await callback.message.edit_text(
        "Введите <b>количество дней</b> прогрева (число).\n"
        "Дата окончания будет рассчитана от даты начала.",
        reply_markup=warmup_cancel_kb(),
    )
    await callback.answer()


@router_warmup_exceptions.message(AddWarmup.waiting_edit_days)
async def msg_edit_days(message: Message, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(message.from_user.id):
        return
    await CreationHelpers.try_delete(message)
    try:
        days = int(message.text.strip())
        if days < 1:
            raise ValueError
    except ValueError:
        await CreationHelpers.edit_bot_msg(
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
    await CreationHelpers.show_confirm(None, state)
