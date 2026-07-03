from dataclasses import dataclass
from aiogram import Bot
from pyrogram import Client
from utils.logger import logger
from config import settings
from utils.database import AccountRepository, decrypt_session
from utils import BotNotifications


@dataclass
class UserBotClient:
    client: Client
    account_id: str
    tg_id: int
    username: str
    phone: str
    ip: str = "unknown"


class ClientManager:
    """Управляет пулом Pyrogram-клиентов, поднятых из шифрованных сессий БД."""

    def __init__(self, bot: Bot):
        self._bot = bot
        self._clients: dict[str, UserBotClient] = {}

    @property
    def clients(self) -> dict[str, UserBotClient]:
        return self._clients

    async def get_or_start(self, account_id: str) -> UserBotClient | None:
        if account_id in self._clients:
            return self._clients[account_id]

        repo = AccountRepository()
        account = await repo.get_by_id(account_id)
        if not account or account.status != "active":
            return None

        # Check if the account belongs to an active warmup group with a proxy
        from utils.database.db_engine import get_session_factory
        from utils.database.models import WarmupGroup, WarmupGroupMember, Proxy
        from sqlalchemy import select

        proxy_dict = None
        try:
            async with get_session_factory()() as session:
                stmt = (
                    select(Proxy)
                    .join(WarmupGroup, WarmupGroup.proxy_id == Proxy.id)
                    .join(WarmupGroupMember, WarmupGroupMember.group_id == WarmupGroup.id)
                    .where(
                        WarmupGroupMember.account_id == account_id,
                        WarmupGroup.status.in_(["enabled", "paused"])
                    )
                )
                res = await session.execute(stmt)
                proxy_obj = res.scalar_one_or_none()
                if proxy_obj:
                    proxy_dict = {
                        "scheme": proxy_obj.proxy_type,
                        "hostname": proxy_obj.host,
                        "port": proxy_obj.port,
                    }
                    if proxy_obj.username:
                        proxy_dict["username"] = decrypt_session(proxy_obj.username)
                    if proxy_obj.password:
                        proxy_dict["password"] = decrypt_session(proxy_obj.password)
        except Exception as e:
            logger.warning(f"Failed to check proxy for account {account_id}: {e}")

        # Check and log external IP address
        actual_ip = await get_client_ip(proxy_dict)
        proxy_desc = f"{proxy_dict['scheme']}://{proxy_dict['hostname']}:{proxy_dict['port']}" if proxy_dict else "direct connection"
        logger.info(f"Checking IP for account {account.phone} using {proxy_desc} -> External IP: {actual_ip}")

        try:
            session_string = decrypt_session(account.session_data)
            client = Client(
                name=str(account.tg_id),
                api_id=settings.API_ID,
                api_hash=settings.API_HASH,
                session_string=session_string,
                in_memory=True,
                proxy=proxy_dict,
            )
            await client.start()
        except Exception as e:
            logger.error(f"Cannot start client for {account.phone}: {e}")
            await BotNotifications.notify_session_revoked(
                self._bot, account.tg_id, account.phone, type(e).__name__
            )
            return None

        userbot = UserBotClient(
            client=client,
            account_id=account.id,
            tg_id=account.tg_id,
            username=account.username or "",
            phone=account.phone,
            ip=actual_ip,
        )
        self._clients[account_id] = userbot
        logger.info(
            f"Pyrogram session up: @{userbot.username} ({userbot.phone}) [IP: {actual_ip}]")
        return userbot


async def get_client_ip(proxy_dict: dict | None = None) -> str:
    import socks
    import socket
    import asyncio

    def _fetch():
        s = socks.socksocket()
        if proxy_dict:
            scheme_str = proxy_dict.get("scheme", "socks5").lower()
            if scheme_str == "socks5":
                proxy_type = socks.SOCKS5
            elif scheme_str == "socks4":
                proxy_type = socks.SOCKS4
            else:
                proxy_type = socks.HTTP
                
            s.set_proxy(
                proxy_type=proxy_type,
                addr=proxy_dict.get("hostname"),
                port=proxy_dict.get("port"),
                username=proxy_dict.get("username"),
                password=proxy_dict.get("password")
            )
        s.settimeout(5.0)
        try:
            s.connect(("api.ipify.org", 80))
            s.sendall(b"GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
            response = s.recv(1024)
            s.close()
            lines = response.decode("utf-8", errors="ignore").split("\r\n")
            for line in reversed(lines):
                if line.strip() and not line.startswith("HTTP/") and not ":" in line and not "Content-" in line:
                    return line.strip()
            return lines[-1].strip()
        except Exception as e:
            return f"failed ({e})"

    return await asyncio.to_thread(_fetch)

    async def stop(self, account_id: str) -> None:
        userbot = self._clients.pop(account_id, None)
        if userbot is None:
            return
        try:
            await userbot.client.stop()
        except Exception:
            pass

    async def stop_all(self) -> None:
        for account_id in list(self._clients.keys()):
            await self.stop(account_id)
