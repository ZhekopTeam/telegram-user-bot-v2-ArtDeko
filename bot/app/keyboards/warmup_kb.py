from datetime import datetime, timedelta, date
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils import SessionRepository

MAX_ACCOUNTS_PER_GROUP = 6


def warmup_list_kb(
    groups: list[tuple[str, str, str, str, int]],
    show_finished_btn: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group_id, name, status, dates, count in groups:
        if status not in ("enabled", "paused"):
            continue
        icon = {"enabled": "🟢", "paused": "⏸"}.get(status, "❔")
        builder.button(
            text=f"{icon} {name} ({count}) | {dates}",
            callback_data=f"warmup:{group_id}",
        )
    builder.adjust(1)

    controls = InlineKeyboardBuilder()
    if show_finished_btn:
        controls.button(text="✅ Завершено", callback_data="warmup_finished_list")
    controls.button(text="➕ Новая группа", callback_data="warmup_add")
    controls.button(text="← Меню", callback_data="menu:main")
    controls.adjust(1)
    builder.attach(controls)
    return builder.as_markup()


def warmup_finished_list_kb(groups: list[tuple[str, str, str, str, int]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group_id, name, status, dates, count in groups:
        if status != "finished":
            continue
        builder.button(
            text=f"✅ {name} ({count}) | {dates}",
            callback_data=f"warmup:{group_id}",
        )
    builder.button(text="← Назад", callback_data="menu:warmup")
    builder.adjust(1)
    return builder.as_markup()


def warmup_detail_kb(group_id: str, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "finished":
        builder.button(text="🏁 Завершить",
                       callback_data=f"warmup_complete:{group_id}")
        builder.button(text="← Назад", callback_data="warmup_finished_list")
    else:
        if status == "enabled":
            builder.button(text="⏸ Поставить на паузу",
                           callback_data=f"warmup_pause:{group_id}")
        elif status == "paused":
            builder.button(text="▶️ Возобновить",
                           callback_data=f"warmup_resume:{group_id}")
        builder.button(text="📋 Очередь",
                       callback_data=f"warmup_queue:{group_id}")
        builder.button(text="➕ Продлить прогрев",
                       callback_data=f"warmup_extend:{group_id}")
        builder.button(text="🏁 Завершить",
                       callback_data=f"warmup_complete:{group_id}")
        builder.button(text="🔄 Обновить",
                       callback_data=f"warmup_refresh:{group_id}")
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
    at_limit = len(selected) >= MAX_ACCOUNTS_PER_GROUP
    for account_id, phone, status in accounts:
        if status != "active":
            continue
        if account_id in selected:
            pos = selected.index(account_id) + 1
            label = f"✅ {pos}. {SessionRepository.mask_phone(phone)}"
            builder.button(
                text=label,
                callback_data=f"pick_acc:{account_id}",
            )
        elif not at_limit:
            builder.button(
                text=SessionRepository.mask_phone(phone),
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
    builder.button(text="5 дней", callback_data="warmup_days:5")
    builder.button(text="7 дней (неделя)", callback_data="warmup_days:7")
    builder.button(text="14 дней (две недели)", callback_data="warmup_days:14")
    builder.button(text="30 дней (месяц)", callback_data="warmup_days:30")
    builder.button(text="✖️ Отмена", callback_data="menu:warmup")
    builder.adjust(1)
    return builder.as_markup()


def warmup_proxy_kb(proxies: list) -> InlineKeyboardMarkup:
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


def warmup_confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Всё верно", callback_data="warmup_confirm_ok")
    builder.button(text="✏️ Редактировать", callback_data="warmup_confirm_edit")
    builder.adjust(1)
    return builder.as_markup()


def warmup_edit_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Дата начала", callback_data="warmup_edit_start")
    builder.button(text="🔢 Количество дней", callback_data="warmup_edit_days")
    builder.button(text="← Назад", callback_data="warmup_edit_back")
    builder.adjust(1)
    return builder.as_markup()


def warmup_extend_kb(group_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="3 дня", callback_data=f"warmup_do_extend:{group_id}:3")
    builder.button(text="5 дней", callback_data=f"warmup_do_extend:{group_id}:5")
    builder.button(text="7 дней (неделя)", callback_data=f"warmup_do_extend:{group_id}:7")
    builder.button(text="14 дней (две недели)", callback_data=f"warmup_do_extend:{group_id}:14")
    builder.button(text="✖️ Отмена", callback_data=f"warmup:{group_id}")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

