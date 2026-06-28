from datetime import datetime, timedelta, date
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
    builder.button(text="🌐 Прокси", callback_data="menu:proxy")
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


# ── Warmup list / detail ──────────────────────────────────────────

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
    builder.button(text="🔄 Обновить",
                   callback_data=f"warmup_refresh:{group_id}")
    builder.button(text="← К списку", callback_data="menu:warmup")
    builder.adjust(1)
    return builder.as_markup()


def warmup_queue_kb(group_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data=f"warmup:{group_id}")
    return builder.as_markup()


# ── Warmup creation flow ──────────────────────────────────────────

MAX_ACCOUNTS_PER_GROUP = 6


def accounts_multipick_kb(
    accounts: list[tuple[str, str, str]],
    selected: list[str],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    at_limit = len(selected) >= MAX_ACCOUNTS_PER_GROUP
    for account_id, phone, status in accounts:
        if status != "active":
            continue
        if account_id in selected:
            pos = selected.index(account_id) + 1
            label = f"✅ {pos}. {mask_phone(phone)}"
            builder.button(
                text=label,
                callback_data=f"pick_acc:{account_id}",
            )
        elif not at_limit:
            builder.button(
                text=mask_phone(phone),
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


def warmup_start_date_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    today_str = today.strftime("%d.%m.%Y")
    tomorrow_str = tomorrow.strftime("%d.%m.%Y")

    builder.button(text="сегодня", callback_data=f"warmup_start_date:{today_str}")
    builder.button(text="завтра", callback_data=f"warmup_start_date:{tomorrow_str}")
    builder.button(text="другая дата", callback_data="warmup_start_date:other")
    builder.button(text="✖️ Отмена", callback_data="menu:warmup")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def warmup_end_date_kb(start_date: date) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    d5 = start_date + timedelta(days=5)
    d7 = start_date + timedelta(days=7)
    d14 = start_date + timedelta(days=14)

    d5_str = d5.strftime("%d.%m.%Y")
    d7_str = d7.strftime("%d.%m.%Y")
    d14_str = d14.strftime("%d.%m.%Y")

    builder.button(text="через 5 дней", callback_data=f"warmup_end_date:{d5_str}")
    builder.button(text="через неделю", callback_data=f"warmup_end_date:{d7_str}")
    builder.button(text="через две недели", callback_data=f"warmup_end_date:{d14_str}")
    builder.button(text="другая дата", callback_data="warmup_end_date:other")
    builder.button(text="✖️ Отмена", callback_data="menu:warmup")
    builder.adjust(1)
    return builder.as_markup()


# ── Proxy selection (during warmup creation) ──────────────────────

def warmup_proxy_kb(proxies: list) -> InlineKeyboardMarkup:
    """proxies: list of (id, name, proxy_type, host, port)"""
    builder = InlineKeyboardBuilder()
    for proxy_id, name, ptype, host, port in proxies:
        builder.button(
            text=f"🌐 {name} ({ptype}://{host}:{port})",
            callback_data=f"warmup_pick_proxy:{proxy_id}",
        )
    builder.button(text="🚫 Без прокси", callback_data="warmup_no_proxy")
    builder.button(text="✖️ Отмена", callback_data="menu:warmup")
    builder.adjust(1)
    return builder.as_markup()


def warmup_no_proxy_warning_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Выбрать прокси", callback_data="warmup_select_proxy_back")
    builder.button(text="➡️ Продолжить без прокси", callback_data="warmup_no_proxy_confirm")
    builder.adjust(1)
    return builder.as_markup()


# ── Confirmation & edit (during warmup creation) ──────────────────

def warmup_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Всё верно", callback_data="warmup_confirm_ok")
    builder.button(text="✏️ Редактировать", callback_data="warmup_confirm_edit")
    builder.adjust(1)
    return builder.as_markup()


def warmup_edit_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Дата начала", callback_data="warmup_edit_start")
    builder.button(text="📅 Дата окончания", callback_data="warmup_edit_end")
    builder.button(text="🔢 Количество дней", callback_data="warmup_edit_days")
    builder.button(text="← Назад", callback_data="warmup_edit_back")
    builder.adjust(1)
    return builder.as_markup()


# ── Proxy management menu ─────────────────────────────────────────

def proxy_list_kb(proxies: list) -> InlineKeyboardMarkup:
    """proxies: list of (id, name, proxy_type, host, port)"""
    builder = InlineKeyboardBuilder()
    for proxy_id, name, ptype, host, port in proxies:
        builder.button(
            text=f"🌐 {name} ({ptype}://{host}:{port})",
            callback_data=f"proxy_detail:{proxy_id}",
        )
    builder.button(text="➕ Добавить прокси", callback_data="proxy_add")
    builder.button(text="← Меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def proxy_detail_kb(proxy_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить", callback_data=f"proxy_del:{proxy_id}")
    builder.button(text="← Назад", callback_data="menu:proxy")
    builder.adjust(1)
    return builder.as_markup()


def proxy_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data="menu:proxy")
    return builder.as_markup()
