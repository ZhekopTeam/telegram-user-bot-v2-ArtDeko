from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from utils.accounts_auth import AccountAuth
from utils.FSM import AddAccount
from utils.logger import logger
from utils.admin_access import is_admin
from utils import SessionRepository, SheetsSync
from app.keyboards import (
    build_code_message,
    auth_code_kb,
    accounts_list_kb,
    back_to_main_kb
)

router_accounts = Router(name="accounts")


@router_accounts.callback_query(F.data == "add_account")
async def cb_add_account(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddAccount.waiting_phone)
    await callback.message.edit_text(
        "Введите <b>номер телефона</b> аккаунта (например, <code>+79991112233</code>):",
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()


@router_accounts.message(AddAccount.waiting_phone)
async def handle_phone(message: Message, state: FSMContext, account_auth: AccountAuth) -> None:
    phone = message.text.strip()
    try:
        await account_auth.start_auth(message.from_user.id, phone)
        await state.update_data(code="")
        await state.set_state(AddAccount.waiting_code)
        await message.answer(
            text=build_code_message(""),
            reply_markup=auth_code_kb(),
        )
    except FileExistsError:
        await state.clear()
        accounts = await SessionRepository.get_session_accounts()
        await message.answer(
            f"Аккаунт {phone} уже авторизован.",
            reply_markup=accounts_list_kb(accounts),
        )
    except Exception as e:
        logger.error(f"Auth start error: {e}")
        await state.clear()
        accounts = await SessionRepository.get_session_accounts()
        await message.answer(
            f"Ошибка при отправке кода: {e}",
            reply_markup=accounts_list_kb(accounts),
        )


@router_accounts.message(AddAccount.waiting_code)
async def handle_code_as_text(message: Message, state: FSMContext, account_auth: AccountAuth) -> None:
    await message.delete()
    await account_auth.cancel()
    await state.clear()
    accounts = await SessionRepository.get_session_accounts()
    await message.answer(
        "❌ Авторизация сброшена.\n\n"
        "Код вводится через кнопки, а не сообщением.",
        reply_markup=accounts_list_kb(accounts),
    )


@router_accounts.callback_query(F.data.startswith("code:"), StateFilter(AddAccount.waiting_code))
async def handle_code_press(callback: CallbackQuery, state: FSMContext, account_auth: AccountAuth) -> None:
    data = await state.get_data()
    code = data.get("code", "")
    key = callback.data.split(":", 1)[1]

    if key == "⌫":
        code = code[:-1]
    elif key == "OK":
        try:
            result = await account_auth.confirm_code(callback.from_user.id, code)
            if result == "ok":
                await state.clear()
                accounts = await SessionRepository.get_session_accounts()
                await callback.message.edit_text(
                    "✅ Аккаунт успешно добавлен!",
                    reply_markup=accounts_list_kb(accounts),
                )
                await SheetsSync.sync_accounts()
            elif result == "need_password":
                await state.set_state(AddAccount.waiting_password)
                await callback.message.edit_text("🔐 Введите пароль 2FA сообщением:")
        except Exception as e:
            await state.clear()
            accounts = await SessionRepository.get_session_accounts()
            await callback.message.edit_text(
                f"Ошибка: {e}",
                reply_markup=accounts_list_kb(accounts),
            )
        await callback.answer()
        return
    else:
        if len(code) < 5:
            code += key

    await state.update_data(code=code)
    await callback.message.edit_text(
        text=build_code_message(code),
        reply_markup=auth_code_kb(),
    )
    await callback.answer()


@router_accounts.message(AddAccount.waiting_password)
async def handle_password(message: Message, state: FSMContext, account_auth: AccountAuth) -> None:
    password = message.text.strip()
    await message.delete()
    try:
        await account_auth.confirm_password(message.from_user.id, password)
        await state.clear()
        accounts = await SessionRepository.get_session_accounts()
        await message.answer(
            "✅ Аккаунт успешно добавлен!",
            reply_markup=accounts_list_kb(accounts),
        )
        await SheetsSync.sync_accounts()
    except Exception as e:
        logger.error(f"Password confirm error: {e}")
        await account_auth.cancel()
        await state.clear()
        accounts = await SessionRepository.get_session_accounts()
        await message.answer(
            f"Неверный пароль или ошибка: {e}",
            reply_markup=accounts_list_kb(accounts),
        )
