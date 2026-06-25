from dataclasses import dataclass
from aiogram import Bot
from pyrogram import Client
from utils.logger import logger
from config import settings
from utils.database import AccountRepository, decrypt_session
from utils.bot_notifications import notify_session_revoked


@dataclass
class UserBotClient:
    client: Client
    account_id: str
    tg_id: int
    username: str
    phone: str


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

        try:
            session_string = decrypt_session(account.session_data)
            client = Client(
                name=str(account.tg_id),
                api_id=settings.API_ID,
                api_hash=settings.API_HASH,
                session_string=session_string,
                in_memory=True,
            )
            await client.start()
        except Exception as e:
            logger.error(f"Cannot start client for {account.phone}: {e}")
            await notify_session_revoked(
                self._bot, account.tg_id, account.phone, type(e).__name__
            )
            return None

        userbot = UserBotClient(
            client=client,
            account_id=account.id,
            tg_id=account.tg_id,
            username=account.username or "",
            phone=account.phone,
        )
        self._clients[account_id] = userbot
        logger.info(
            f"Pyrogram session up: @{userbot.username} ({userbot.phone})")
        return userbot

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
