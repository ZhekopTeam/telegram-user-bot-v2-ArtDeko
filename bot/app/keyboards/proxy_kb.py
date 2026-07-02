from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def proxy_list_kb(proxies: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for proxy_id, name, ptype, host, port, is_busy in proxies:
        status = "🔴" if is_busy else "🟢"
        builder.button(
            text=f"{status} {host}:{port}",
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
