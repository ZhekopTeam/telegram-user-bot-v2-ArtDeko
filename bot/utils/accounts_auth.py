from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
from config import settings
from utils.database import Account, AccountRepository, encrypt_session
from utils.logger import logger


@dataclass
class AccountInAuth:
    client: Client
    phone: str
    phone_code_hash: str
    session_name: str
    admin_tg_id: int


class AccountAuth:
    def __init__(self):
        self.account_in_auth: Optional[AccountInAuth] = None

    async def start_auth(self, admin_tg_id: int, phone: str):
        if admin_tg_id not in settings.admins_list:
            raise PermissionError("User is not admin")

        Path(settings.SESSIONS_DIR).mkdir(parents=True, exist_ok=True)

        existing = await AccountRepository().get_by_phone(phone)
        if existing and existing.status == "active":
            raise FileExistsError(f"Аккаунт {phone} уже авторизован.")

        session_name = str(uuid4())

        client = Client(
            name=session_name,
            api_id=settings.API_ID,
            api_hash=settings.API_HASH,
            in_memory=True,
        )

        await client.connect()
        sent = await client.send_code(phone)

        self.account_in_auth = AccountInAuth(
            client=client,
            phone=phone,
            phone_code_hash=sent.phone_code_hash,
            session_name=session_name,
            admin_tg_id=admin_tg_id,
        )

        logger.info(f"Auth started for {phone} (admin_id={admin_tg_id})")
        return client

    async def confirm_code(self, admin_tg_id: int, code: str) -> str:
        if admin_tg_id not in settings.admins_list:
            raise PermissionError("User is not admin")

        data = self.account_in_auth
        clean_code = "".join(filter(str.isdigit, code))

        try:
            await data.client.sign_in(
                phone_number=data.phone,
                phone_code_hash=data.phone_code_hash,
                phone_code=clean_code,
            )
            await self._finalize()
            return "ok"

        except SessionPasswordNeeded:
            return "need_password"

        except Exception as e:
            logger.exception(f"sign_in error: {e}")
            await self.cancel()
            raise

    async def confirm_password(self, admin_tg_id: int, password: str) -> None:
        if admin_tg_id not in settings.admins_list:
            raise PermissionError("User is not admin")

        await self.account_in_auth.client.check_password(password)
        await self._finalize()

    async def _finalize(self) -> None:
        data = self.account_in_auth
        session_string = await data.client.export_session_string()
        me = await data.client.get_me()
        await data.client.disconnect()

        temp_file = Path(settings.SESSIONS_DIR) / \
            f"{data.session_name}.session"
        if temp_file.exists():
            temp_file.unlink()

        repo = AccountRepository()
        existing = await repo.get_by_phone(data.phone)

        if existing:
            await repo.reactivate(me.id, encrypt_session(session_string), data.admin_tg_id)
        else:
            await repo.add(Account(
                id=data.session_name,
                tg_id=me.id,
                phone=data.phone,
                username=me.username or me.first_name or "",
                is_premium=bool(me.is_premium),
                session_data=encrypt_session(session_string),
                admin_tg_id=data.admin_tg_id,
            ))

        self.account_in_auth = None
        logger.info(
            f"Account {data.phone} authorized, session encrypted in DB.")

    async def cancel(self) -> None:
        if not self.account_in_auth:
            return
        try:
            await self.account_in_auth.client.disconnect()
        except Exception:
            pass
        session_file = Path(settings.SESSIONS_DIR) / \
            f"{self.account_in_auth.session_name}.session"
        if session_file.exists():
            session_file.unlink()
        self.account_in_auth = None
        logger.info("Auth cancelled")
