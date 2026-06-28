from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Аккаунты", callback_data="menu:accounts")
    builder.button(text="🔥 Прогрев", callback_data="menu:warmup")
    builder.button(text="🌐 Прокси", callback_data="menu:proxy")
    builder.adjust(1)
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Меню", callback_data="menu:main")
    return builder.as_markup()
