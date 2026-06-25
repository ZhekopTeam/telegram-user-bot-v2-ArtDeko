from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.session_repo import mask_phone


def build_code_message(code: str) -> str:
    dots = "●" * len(code)
    empty = "○" * (5 - len(code))
    return f"🔐 Введите код:\n\n{dots}{empty}"


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Аккаунты", callback_data="menu:accounts")
    builder.button(text="🔥 Прогрев", callback_data="menu:warmup")
    builder.adjust(1)
    return builder.as_markup()


def accounts_list_kb(accounts: list[tuple[str, str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account_id, phone, status in accounts:
        prefix = "⚠️ " if status != "active" else ""
        builder.button(
            text=f"{prefix}{mask_phone(phone)}",
            callback_data=f"account:{account_id}",
        )
    builder.button(text="➕ Добавить аккаунт", callback_data="add_account")
    builder.button(text="← Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Меню", callback_data="menu:main")
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


def warmup_list_kb(groups: list[tuple[str, str, str, str, int]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group_id, name, status, dates, count in groups:
        icon = {"enabled": "🟢", "paused": "⏸",
                "finished": "✅"}.get(status, "❔")
        builder.button(
            text=f"{icon} {name} ({count}) | {dates}",
            callback_data=f"warmup:{group_id}",
        )
    builder.button(text="➕ Новая группа", callback_data="warmup_add")
    builder.button(text="← Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def warmup_detail_kb(group_id: str, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "enabled":
        builder.button(text="⏸ Поставить на паузу",
                       callback_data=f"warmup_pause:{group_id}")
    elif status == "paused":
        builder.button(text="▶️ Возобновить",
                       callback_data=f"warmup_resume:{group_id}")
    builder.button(text="📋 Очередь",
                   callback_data=f"warmup_queue:{group_id}")
    builder.button(text="🗑 Удалить группу",
                   callback_data=f"warmup_del:{group_id}")
    builder.button(text="← К списку", callback_data="menu:warmup")
    builder.adjust(1)
    return builder.as_markup()


def warmup_queue_kb(group_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data=f"warmup:{group_id}")
    return builder.as_markup()


def accounts_multipick_kb(
    accounts: list[tuple[str, str, str]],
    selected: list[str],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for account_id, phone, status in accounts:
        if status != "active":
            continue
        if account_id in selected:
            pos = selected.index(account_id) + 1
            label = f"✅ {pos}. {mask_phone(phone)}"
        else:
            label = mask_phone(phone)
        builder.button(
            text=label,
            callback_data=f"pick_acc:{account_id}",
        )
    if len(selected) >= 2:
        builder.button(text="✓ Готово", callback_data="warmup_accs_done")
    builder.button(text="✖️ Отмена", callback_data="menu:warmup")
    builder.adjust(1)
    return builder.as_markup()


def warmup_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data="menu:warmup")
    return builder.as_markup()
