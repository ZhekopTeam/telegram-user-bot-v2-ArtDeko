from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from utils.FSM import AddAdmin
from utils import CreationHelpers
from utils.admin_access import (
    is_owner,
    is_admin,
    owner_ids,
    db_admin_ids,
    add_admin,
    remove_admin,
)
from utils.logger import logger
from app.keyboards import admin_list_kb, admin_cancel_kb


router_admin = Router(name="admin")


def _admin_list_text() -> str:
    lines = ["👤 <b>Администраторы бота</b>\n"]
    for tg_id in owner_ids():
        lines.append(f"• <code>{tg_id}</code> — владелец")
    for tg_id in db_admin_ids():
        lines.append(f"• <code>{tg_id}</code> — добавлен")
    if not owner_ids() and not db_admin_ids():
        lines.append("Список пуст.")
    lines.append(
        "\nВладельцы задаются разработчиком и не удаляются через бота."
    )
    return "\n".join(lines)


@router_admin.callback_query(F.data == "menu:admins")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(
        _admin_list_text(),
        reply_markup=admin_list_kb(db_admin_ids()),
    )
    await callback.answer()


@router_admin.callback_query(F.data == "admin_add")
async def cb_admin_add(callback: CallbackQuery, state: FSMContext) -> None:
    """
    For adding new owners to the bot
    Owners are set in the ADMINS list in the .env file
    Owners are not deleted through the bot
    Owners can add and delete other admins
    """
    if not is_owner(callback.from_user.id):
        await callback.answer()
        return
    await state.update_data(
        bot_chat_id=callback.message.chat.id,
        bot_message_id=callback.message.message_id,
    )
    await state.set_state(AddAdmin.waiting_tg_id)
    await callback.message.edit_text(
        "Введите <b>Telegram ID</b> нового администратора.\n\n"
        "Пользователь сможет управлять ботом, но не сможет "
        "добавлять или удалять других админов.\n\n",
        reply_markup=admin_cancel_kb(),
    )
    await callback.answer()


@router_admin.message(AddAdmin.waiting_tg_id)
async def msg_admin_tg_id(message: Message, state: FSMContext) -> None:
    if not is_owner(message.from_user.id):
        return
    await CreationHelpers.try_delete(message)
    text = message.text.strip()
    try:
        tg_id = int(text)
        if tg_id <= 0:
            raise ValueError
    except ValueError:
        await CreationHelpers.edit_bot_msg(
            state,
            "❌ Неверный формат. Введите числовой Telegram ID, например "
            "<code>123456789</code>:",
            reply_markup=admin_cancel_kb(),
        )
        return

    if is_admin(tg_id):
        await CreationHelpers.edit_bot_msg(
            state,
            f"❌ <code>{tg_id}</code> уже является администратором.",
            reply_markup=admin_cancel_kb(),
        )
        return

    await add_admin(tg_id)
    await state.clear()
    logger.info(f"Admin {tg_id} added by owner {message.from_user.id}")
    await CreationHelpers.edit_bot_msg(
        state,
        f"✅ Администратор <code>{tg_id}</code> добавлен.\n\n"
        + _admin_list_text(),
        reply_markup=admin_list_kb(db_admin_ids()),
    )


@router_admin.callback_query(F.data.startswith("admin_del:"))
async def cb_admin_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await callback.answer()
        return
    tg_id = int(callback.data.split(":", 1)[1])
    if not await remove_admin(tg_id):
        await callback.answer("Нельзя удалить этого админа", show_alert=True)
        return
    logger.info(f"Admin {tg_id} removed by owner {callback.from_user.id}")
    await state.clear()
    await callback.message.edit_text(
        _admin_list_text(),
        reply_markup=admin_list_kb(db_admin_ids()),
    )
    await callback.answer("🗑 Удалено")
