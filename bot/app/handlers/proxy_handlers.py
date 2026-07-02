import re
from uuid import uuid4
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from config import settings
from utils.FSM import AddProxy
from utils.database import Proxy, ProxyRepository, encrypt_session, decrypt_session
from app.keyboards import (
    proxy_list_kb,
    proxy_detail_kb,
    proxy_cancel_kb,
)

router_proxy = Router(name="proxy")


def is_admin(tg_id: int) -> bool:
    return tg_id in settings.admins_list


async def _proxy_rows() -> list[tuple[str, str, str, str, int]]:
    proxies = await ProxyRepository().get_all()
    return [(p.id, p.name, p.proxy_type, p.host, p.port) for p in proxies]


@router_proxy.callback_query(F.data == "menu:proxy")
async def cb_proxy_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.clear()
    rows = await _proxy_rows()
    text = (
        f"🌐 <b>Прокси</b> ({len(rows)}):" if rows
        else "🌐 Прокси не добавлены."
    )
    await callback.message.edit_text(text, reply_markup=proxy_list_kb(rows))
    await callback.answer()


@router_proxy.callback_query(F.data.startswith("proxy_detail:"))
async def cb_proxy_detail(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    proxy_id = callback.data.split(":", 1)[1]
    repo = ProxyRepository()
    proxy = await repo.get_by_id(proxy_id)
    if not proxy:
        await callback.answer("Прокси не найден", show_alert=True)
        return

    decrypted_user = decrypt_session(proxy.username) if proxy.username else None
    auth = f"{decrypted_user}:***@" if decrypted_user else ""
    text = (
        f"🌐 <b>{proxy.name}</b>\n\n"
        f"Тип: <code>{proxy.proxy_type}</code>\n"
        f"Адрес: <code>{auth}{proxy.host}:{proxy.port}</code>"
    )
    await callback.message.edit_text(
        text, reply_markup=proxy_detail_kb(proxy.id))
    await callback.answer()


@router_proxy.callback_query(F.data.startswith("proxy_del:"))
async def cb_proxy_delete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    proxy_id = callback.data.split(":", 1)[1]
    await ProxyRepository().delete(proxy_id)
    await callback.answer("🗑 Удалено")
    rows = await _proxy_rows()
    text = (
        f"🌐 <b>Прокси</b> ({len(rows)}):" if rows
        else "🌐 Прокси не добавлены."
    )
    await callback.message.edit_text(text, reply_markup=proxy_list_kb(rows))


@router_proxy.callback_query(F.data == "proxy_add")
async def cb_proxy_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AddProxy.waiting_proxy_input)
    await callback.message.edit_text(
        "Введите прокси в формате:\n"
        "<code>тип://логин:пароль@хост:порт</code>\n\n"
        "Или без авторизации:\n"
        "<code>тип://хост:порт</code>\n\n"
        "Типы: <code>socks5</code>, <code>socks4</code>, <code>http</code>\n\n"
        "Пример: <code>socks5://user:pass@1.2.3.4:1080</code>",
        reply_markup=proxy_cancel_kb(),
    )
    await callback.answer()


def parse_proxy(text: str) -> dict | None:
    text = text.strip()
    
    # 1. Extract protocol if present
    ptype = "socks5"
    prefix_match = re.match(r"^(socks5|socks4|http)(?::/+|[ \t]+)", text, re.IGNORECASE)
    if prefix_match:
        ptype = prefix_match.group(1).lower()
        text = text[prefix_match.end():].strip()
        
    # 2. Try at-match (user:pass@host:port)
    at_match = re.match(r"^([^:]+):([^@]+)@([^:]+):(\d+)$", text)
    if at_match:
        return {
            "ptype": ptype,
            "username": at_match.group(1),
            "password": at_match.group(2),
            "host": at_match.group(3),
            "port": int(at_match.group(4))
        }
        
    # 3. Try colon-4-match (host:port:user:pass)
    colon_4_match = re.match(r"^([^:]+):(\d+):([^:]+):([^:]+)$", text)
    if colon_4_match:
        return {
            "ptype": ptype,
            "username": colon_4_match.group(3),
            "password": colon_4_match.group(4),
            "host": colon_4_match.group(1),
            "port": int(colon_4_match.group(2))
        }
        
    # 4. Try colon-2-match (host:port)
    colon_2_match = re.match(r"^([^:]+):(\d+)$", text)
    if colon_2_match:
        return {
            "ptype": ptype,
            "username": None,
            "password": None,
            "host": colon_2_match.group(1),
            "port": int(colon_2_match.group(2))
        }
        
    return None


@router_proxy.message(AddProxy.waiting_proxy_input)
async def msg_proxy_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip()
    parsed = parse_proxy(text)
    if not parsed:
        await message.answer(
            "❌ Неверный формат.\n"
            "Вы можете ввести в одном из следующих форматов:\n"
            "• <code>socks5://user:pass@host:port</code>\n"
            "• <code>SOCKS5 host:port:user:pass</code>\n"
            "• <code>host:port:user:pass</code>",
            reply_markup=proxy_cancel_kb(),
        )
        return

    ptype = parsed["ptype"]
    username = parsed["username"]
    password = parsed["password"]
    host = parsed["host"]
    port = parsed["port"]

    name = f"{host}:{port}"
    
    enc_user = encrypt_session(username) if username else None
    enc_pass = encrypt_session(password) if password else None

    proxy = Proxy(
        id=str(uuid4()),
        name=name,
        proxy_type=ptype,
        host=host,
        port=port,
        username=enc_user,
        password=enc_pass,
    )
    await ProxyRepository().add(proxy)
    await state.clear()

    rows = await _proxy_rows()
    text_msg = f"✅ Прокси добавлен!\n\n🌐 <b>Прокси</b> ({len(rows)}):"
    await message.answer(text_msg, reply_markup=proxy_list_kb(rows))
