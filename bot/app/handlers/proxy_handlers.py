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


_PROXY_RE = re.compile(
    r"^(socks5|socks4|http)://"
    r"(?:([^:]+):([^@]+)@)?"
    r"([^:]+):(\d+)$",
    re.IGNORECASE,
)


@router_proxy.message(AddProxy.waiting_proxy_input)
async def msg_proxy_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip()
    m = _PROXY_RE.match(text)
    if not m:
        await message.answer(
            "❌ Неверный формат.\n"
            "Пример: <code>socks5://user:pass@1.2.3.4:1080</code>",
            reply_markup=proxy_cancel_kb(),
        )
        return

    ptype = m.group(1).lower()
    username = m.group(2)
    password = m.group(3)
    host = m.group(4)
    port = int(m.group(5))

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
