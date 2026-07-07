from datetime import datetime, timezone, date, timedelta
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from utils.logger import logger
from utils.admin_access import is_admin
from utils import SessionRepository, SheetsSync
from utils.database import (
    WarmupGroupRepository,
    ScheduledMessageRepository,
    AccountRepository,
    ProxyRepository,
)
from utils.FSM import AddWarmup
from app.keyboards import (
    warmup_list_kb,
    warmup_finished_list_kb,
    warmup_detail_kb,
    warmup_queue_kb,
    warmup_extend_kb,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

router_warmup_menu = Router(name="warmup_menu")

_MESSAGE_STATUS_LABELS = {
    "pending": "Ожидает",
    "sent": "Отправлено",
    "failed": "Ошибка",
    "cancelled": "Отменено",
}


async def build_groups_view() -> list[tuple[str, str, str, str, int]]:
    repo = WarmupGroupRepository()
    groups = await repo.get_all()
    rows: list[tuple[str, str, str, str, int]] = []
    for g in groups:
        members = await repo.get_members(g.id)
        dates = f"{g.start_date.strftime('%d.%m')}–{g.end_date.strftime('%d.%m.%Y')}"
        rows.append((g.id, g.name, g.status, dates, len(members)))
    return rows


async def warmup_text() -> str:
    rows = await build_groups_view()
    if not rows:
        return "🔥 Групп прогрева нет."
    return f"🔥 <b>Группы прогрева</b> ({len(rows)}):"


async def render_detail(callback: CallbackQuery, group_id: str) -> None:
    g_repo = WarmupGroupRepository()
    msg_repo = ScheduledMessageRepository()
    acc_repo = AccountRepository()

    group = await g_repo.get_by_id(group_id)
    if not group:
        await callback.answer("Группа не найдена", show_alert=True)
        return

    members = await g_repo.get_members(group_id)
    accounts = {a.id: a for a in await acc_repo.get_all()}
    chain_lines = []
    for m in members:
        a = accounts.get(m.account_id)
        chain_lines.append(
            f"{m.position + 1}. {SessionRepository.mask_phone(a.phone) if a else '?'}"
        )

    stats = await msg_repo.count_by_status_for_group(group_id)
    stats_str = " | ".join(
        f"{_MESSAGE_STATUS_LABELS.get(k, k)}: {v}"
        for k, v in sorted(stats.items())
    ) or "нет сообщений"

    last_planned = (
        group.last_planned_date.isoformat()
        if group.last_planned_date else "—"
    )

    proxy_line = "—"
    if group.proxy_id:
        proxy = await ProxyRepository().get_by_id(group.proxy_id)
        if proxy:
            proxy_line = f"{proxy.name} ({proxy.proxy_type})"

    text = (
        f"🆔 <code>{group.id[:8]}</code>\n"
        f"📛 <b>{group.name}</b>\n"
        f"📅 {group.start_date} — {group.end_date}\n"
        f"⚙️ Статус: <b>{group.status}</b>\n"
        f"🌐 Прокси: <b>{proxy_line}</b>\n"
        f"🔁 Циклов на пару: {group.cycles_per_pair}\n"
        f"⏱ Интервал: {group.min_interval_min}–{group.max_interval_min} мин\n"
        f"🕘 Окно дня: {group.day_start_hour:02d}:00–{group.day_end_hour:02d}:00\n"
        f"📊 {stats_str}\n"
        f"📌 Последнее планирование: {last_planned}\n\n"
        f"<b>Цепочка:</b>\n" + "\n".join(chain_lines)
    )
    await callback.message.edit_text(
        text, reply_markup=warmup_detail_kb(group.id, group.status))


@router_warmup_menu.callback_query(F.data == "menu:warmup")
async def cb_warmup_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    rows = await build_groups_view()
    has_finished = any(r[2] == "finished" for r in rows)
    await callback.message.edit_text(
        await warmup_text(),
        reply_markup=warmup_list_kb(rows, show_finished_btn=has_finished),
    )
    await callback.answer()


@router_warmup_menu.callback_query(F.data == "warmup_finished_list")
async def cb_warmup_finished_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    rows = await build_groups_view()
    await callback.message.edit_text(
        "✅ <b>Завершённые группы прогрева</b>\n\n"
        "Здесь отображаются группы, которые отработали весь период прогрева. "
        "Перейдите в группу, чтобы подтвердить завершение и освободить аккаунты.",
        reply_markup=warmup_finished_list_kb(rows),
    )
    await callback.answer()


@router_warmup_menu.callback_query(F.data.startswith("warmup_complete:"))
async def cb_warmup_complete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    repo = WarmupGroupRepository()
    group = await repo.get_by_id(group_id)
    group_name = group.name if group else "Без названия"
    
    await repo.delete(group_id)
    await SheetsSync.sync_warmup()
    
    back_builder = InlineKeyboardBuilder()
    back_builder.button(text="← К списку", callback_data="menu:warmup")
    
    await callback.message.edit_text(
        f"🏁 <b>Успешно завершено!</b>\n\n"
        f"Прогрев аккаунтов из группы <b>{group_name}</b> успешно завершён.\n"
        f"Аккаунты освобождены от прогрева и доступны для дальнейших действий.",
        reply_markup=back_builder.as_markup()
    )
    await callback.answer("🏁 Прогрев успешно завершён!")


@router_warmup_menu.callback_query(F.data.startswith("warmup:"))
async def cb_warmup_detail(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await render_detail(callback, group_id)
    await callback.answer()


@router_warmup_menu.callback_query(F.data.startswith("warmup_refresh:"))
async def cb_warmup_refresh(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    try:
        await render_detail(callback, group_id)
        await callback.answer("🔄 Обновлено")
    except Exception as e:
        if "message is not modified" in str(e):
            await callback.answer("✅ Данные актуальны")
        else:
            await callback.answer("Ошибка при обновлении")
            raise e


@router_warmup_menu.callback_query(F.data.startswith("warmup_pause:"))
async def cb_warmup_pause(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    await WarmupGroupRepository().set_status(group_id, "paused")
    await ScheduledMessageRepository().cancel_pending_for_group(group_id)
    await SheetsSync.sync_warmup()
    await render_detail(callback, group_id)
    await callback.answer("⏸ Поставлено на паузу")


@router_warmup_menu.callback_query(F.data.startswith("warmup_resume:"))
async def cb_warmup_resume(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    group_repo = WarmupGroupRepository()
    await group_repo.set_status(group_id, "enabled")

    # Instantly trigger planning for today
    from accounts.warmup_planner import WarmupPlanner
    try:
        group = await group_repo.get_by_id(group_id)
        if group:
            planner = WarmupPlanner()
            await planner.resume_day(group, datetime.now().date())
    except Exception as e:
        logger.error(f"Failed to resume group {group_id}: {e}")

    await SheetsSync.sync_warmup()
    await render_detail(callback, group_id)
    await callback.answer("▶️ Возобновлено")


@router_warmup_menu.callback_query(F.data.startswith("warmup_extend:"))
async def cb_warmup_extend(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    
    await state.update_data(
        extend_group_id=group_id,
        bot_chat_id=callback.message.chat.id,
        bot_message_id=callback.message.message_id,
    )
    await state.set_state(AddWarmup.waiting_extend_days)
    
    await callback.message.edit_text(
        "➕ <b>Продление прогрева</b>\n\n"
        "Введите <b>количество дней</b>, на которое хотите продлить прогрев этой группы (число), или выберите вариант на кнопках ниже:",
        reply_markup=warmup_extend_kb(group_id),
    )
    await callback.answer()


@router_warmup_menu.callback_query(F.data.startswith("warmup_do_extend:"))
async def cb_warmup_do_extend(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    parts = callback.data.split(":")
    group_id = parts[1]
    days = int(parts[2])
    
    await state.clear()
    
    group_repo = WarmupGroupRepository()
    group = await group_repo.get_by_id(group_id)
    if group:
        base_date = max(group.end_date, date.today())
        new_end_date = base_date + timedelta(days=days)
        await group_repo.extend_group(group_id, new_end_date)
        
        from accounts.warmup_planner import WarmupPlanner
        try:
            planner = WarmupPlanner()
            await planner.resume_day(group, date.today())
        except Exception as e:
            logger.error(f"Failed to plan on extend: {e}")
            
    await SheetsSync.sync_warmup()
    await render_detail(callback, group_id)
    await callback.answer("➕ Прогрев успешно продлён!")


@router_warmup_menu.message(AddWarmup.waiting_extend_days)
async def msg_warmup_extend_days(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    
    try:
        await message.delete()
    except Exception:
        pass
        
    try:
        days = int(message.text.strip())
        if days < 1:
            raise ValueError
    except ValueError:
        data = await state.get_data()
        group_id = data["extend_group_id"]
        from utils import CreationHelpers
        await CreationHelpers.edit_bot_msg(
            state,
            "❌ Неверный формат. Введите положительное целое число дней (например, <code>5</code>):\n\n"
            "Введите <b>количество дней</b>, на которое хотите продлить прогрев этой группы:",
            reply_markup=warmup_extend_kb(group_id),
        )
        return
        
    data = await state.get_data()
    group_id = data["extend_group_id"]
    await state.clear()
    
    group_repo = WarmupGroupRepository()
    group = await group_repo.get_by_id(group_id)
    if group:
        base_date = max(group.end_date, date.today())
        new_end_date = base_date + timedelta(days=days)
        await group_repo.extend_group(group_id, new_end_date)
        
        from accounts.warmup_planner import WarmupPlanner
        try:
            planner = WarmupPlanner()
            await planner.resume_day(group, date.today())
        except Exception as e:
            logger.error(f"Failed to plan on extend: {e}")
            
    await SheetsSync.sync_warmup()
    
    class MockMessage:
        def __init__(self, chat_id, message_id):
            self.chat = type("Chat", (), {"id": chat_id})()
            self.message_id = message_id
        async def edit_text(self, text, reply_markup=None, **kwargs):
            from config import bot as tg_bot
            return await tg_bot.edit_message_text(
                text=text,
                chat_id=self.chat.id,
                message_id=self.message_id,
                reply_markup=reply_markup,
            )
            
    class MockCallbackQuery:
        def __init__(self, bot_msg, from_user):
            self.message = bot_msg
            self.from_user = from_user
        async def answer(self, *args, **kwargs):
            pass
            
    bot_msg = MockMessage(data["bot_chat_id"], data["bot_message_id"])
    mock_cb = MockCallbackQuery(bot_msg, message.from_user)
    await render_detail(mock_cb, group_id)



@router_warmup_menu.callback_query(F.data.startswith("warmup_queue:"))
async def cb_warmup_queue(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    group_id = callback.data.split(":", 1)[1]
    msg_repo = ScheduledMessageRepository()
    acc_repo = AccountRepository()
    upcoming = await msg_repo.get_upcoming_for_group(
        group_id, datetime.now(timezone.utc), limit=15)
    accounts = {a.id: a for a in await acc_repo.get_all()}

    if not upcoming:
        text = "📭 Ближайших сообщений нет."
    else:
        lines = []
        for m in upcoming:
            s = accounts.get(m.sender_id)
            r = accounts.get(m.receiver_id)
            ts = m.run_at.astimezone().strftime("%d.%m %H:%M")
            lines.append(
                f"• {ts} | {SessionRepository.mask_phone(s.phone) if s else '?'} → "
                f"{SessionRepository.mask_phone(r.phone) if r else '?'}"
            )
        text = "📋 <b>Ближайшие сообщения:</b>\n\n" + "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=warmup_queue_kb(group_id))
    await callback.answer()
