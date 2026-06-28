from pathlib import Path
from config import settings
from utils.database import AccountRepository, WarmupGroupRepository


class SessionRepository:
    @classmethod
    async def get_session_accounts(cls) -> list[tuple[str, str, str]]:
        repo = AccountRepository()
        accounts = await repo.get_all()
        try:
            busy_ids = await WarmupGroupRepository().get_account_ids_in_active_groups()
        except Exception:
            busy_ids = set()

        res = []
        for a in accounts:
            status = a.status
            if status == "active" and a.id in busy_ids:
                status = "warmup"
            res.append((a.id, a.phone, status))
        return res

    @classmethod
    def mask_phone(cls, phone: str) -> str:
        digits = phone.lstrip("+")
        if len(digits) < 4:
            return phone
        return f"+{digits[0]} *** *** {digits[-4:]}"

    @classmethod
    async def delete_session(cls, phone: str) -> bool:
        repo = AccountRepository()
        account = await repo.get_by_phone(phone)
        if not account:
            return False

        session_file = Path(settings.SESSIONS_DIR) / f"{account.id}.session"
        if session_file.exists():
            session_file.unlink()

        await repo.delete_by_phone(phone)
        return True
