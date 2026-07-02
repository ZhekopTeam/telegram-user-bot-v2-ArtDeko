from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils import SessionRepository


def build_code_message(code: str) -> str:
    dots = "●" * len(code)
    empty = "○" * (5 - len(code))
    return f"🔐 Введите код:\n\n{dots}{empty}"


def accounts_list_kb(accounts: list[tuple[str, str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account_id, phone, status in accounts:
        if status == "active":
            prefix = "🟢 "
        elif status == "warmup":
            prefix = "🔥 "
        else:
            prefix = "⚠️ "
        builder.button(
            text=f"{prefix}{SessionRepository.mask_phone(phone)}",
            callback_data=f"account:{account_id}",
        )
    builder.button(text="➕ Добавить аккаунт", callback_data="add_account")
    builder.button(text="← Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def back_to_accounts_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← К списку аккаунтов", callback_data="menu:accounts")
    return builder.as_markup()


def account_detail_kb(account_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить аккаунт",
                   callback_data=f"delete_account:{account_id}")
    builder.button(text="← Назад", callback_data="menu:accounts")
    builder.adjust(1, 1)
    return builder.as_markup()


def auth_code_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = ["1", "2", "3", "4", "5", "6",
               "7", "8", "9", "⌫", "0", "OK"]
    for b in buttons:
        builder.button(text=b, callback_data=f"code:{b}")
    builder.button(text="← Отмена", callback_data="menu:accounts")
    builder.adjust(3, 3, 3, 3, 1)
    return builder.as_markup()
