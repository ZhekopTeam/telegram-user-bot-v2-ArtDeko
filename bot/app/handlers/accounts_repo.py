from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import settings
from utils import SessionRepository, SheetsSync
from app.keyboards import (
    main_menu_kb,
    accounts_list_kb,
    account_detail_kb,
)
from utils.logger import logger

router_repo = Router(name="repo")


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admins_list


def _menu_text() -> str:
    return (
        "👋 <b>Меню</b>\n\n"
        "• 📱 Аккаунты — добавить/удалить аккаунт для прогрева\n"
        "• 🔥 Прогрев — задачи обмена сообщениями между парами аккаунтов"
    )


async def _accounts_text() -> str:
    accounts = await SessionRepository.get_session_accounts()
    if accounts:
        return f"📱 <b>Авторизованные аккаунты</b> ({len(accounts)}):"
    return "📱 Авторизованных аккаунтов пока нет."


@router_repo.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(_menu_text(), reply_markup=main_menu_kb())


@router_repo.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(_menu_text(), reply_markup=main_menu_kb())
    await callback.answer()


@router_repo.callback_query(F.data == "menu:accounts")
async def cb_accounts(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    accounts = await SessionRepository.get_session_accounts()
    await callback.message.edit_text(
        await _accounts_text(),
        reply_markup=accounts_list_kb(accounts),
    )
    await callback.answer()


@router_repo.callback_query(F.data.startswith("account:"))
async def cb_account_detail(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    account_id = callback.data.split(":", 1)[1]
    accounts = await SessionRepository.get_session_accounts()
    target = next((a for a in accounts if a[0] == account_id), None)
    if not target:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return
    _, phone, status = target

    if status == "active":
        status_emoji = "✅"
    elif status == "warmup":
        status_emoji = "🔥"
    else:
        status_emoji = "⚠️"
    text = f" Статус: <code>{status}</code> {status_emoji}\n\nНомер: <b>{phone}</b>"

    await callback.message.edit_text(
        text, reply_markup=account_detail_kb(account_id))
    await callback.answer()


@router_repo.callback_query(F.data.startswith("delete_account:"))
async def cb_delete_account(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    account_id = callback.data.split(":", 1)[1]
    accounts = await SessionRepository.get_session_accounts()
    target = next((a for a in accounts if a[0] == account_id), None)
    if not target:
        await callback.answer("⚠️ Аккаунт не найден", show_alert=True)
        return

    _, phone, _ = target
    deleted = await SessionRepository.delete_session(phone)
    if deleted:
        logger.info(
            f"Account {phone} deleted by admin {callback.from_user.id}")
        await callback.answer("✅ Сессия удалена")
        await SheetsSync.sync_accounts()
    else:
        await callback.answer("⚠️ Не удалось удалить", show_alert=True)

    accounts = await SessionRepository.get_session_accounts()
    await callback.message.edit_text(
        await _accounts_text(),
        reply_markup=accounts_list_kb(accounts),
    )
