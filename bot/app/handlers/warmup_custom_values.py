from datetime import datetime, date
from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from utils.FSM import AddWarmup
from utils import CreationHelpers
from app.keyboards import (
    warmup_start_date_kb,
    warmup_end_date_kb,
)

router_warmup_custom = Router(name="warmup_custom")


@router_warmup_custom.message(AddWarmup.waiting_start_date)
async def msg_start_date(message: Message, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(message.from_user.id):
        return
    await CreationHelpers.try_delete(message)
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await CreationHelpers.edit_bot_msg(
            state,
            "❌ Неверный формат. Пример: <code>24.05.2026</code>\n\n"
            "Введите <b>дату начала</b> прогрева в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_start_date_kb(),
        )
        return
    await state.update_data(start_date=d.isoformat())
    await state.set_state(AddWarmup.waiting_end_date)
    await CreationHelpers.edit_bot_msg(
        state,
        "Теперь введите <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
        reply_markup=warmup_end_date_kb(d),
    )


@router_warmup_custom.message(AddWarmup.waiting_end_date)
async def msg_end_date(message: Message, state: FSMContext) -> None:
    if not CreationHelpers.is_admin(message.from_user.id):
        return
    await CreationHelpers.try_delete(message)
    try:
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        data = await state.get_data()
        start_date = date.fromisoformat(data["start_date"])
        await CreationHelpers.edit_bot_msg(
            state,
            "❌ Неверный формат. Пример: <code>30.06.2026</code>\n\n"
            "Введите <b>дату окончания</b> в формате <code>дд.мм.гггг</code>:",
            reply_markup=warmup_end_date_kb(start_date),
        )
        return
    await CreationHelpers.proceed_to_proxy(message, state, end_date)
