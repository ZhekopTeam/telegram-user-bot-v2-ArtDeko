from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_list_kb(db_ids: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tg_id in db_ids:
        builder.button(
            text=f"🗑 {tg_id}",
            callback_data=f"admin_del:{tg_id}",
        )
    builder.button(text="➕ Добавить админа", callback_data="admin_add")
    builder.button(text="← Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def admin_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data="menu:admins")
    return builder.as_markup()
