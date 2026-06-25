from pathlib import Path
from config import settings
from utils.database import AccountRepository


async def get_session_accounts() -> list[tuple[str, str, str]]:
    repo = AccountRepository()
    accounts = await repo.get_all()
    return [(a.id, a.phone, a.status) for a in accounts]


def mask_phone(phone: str) -> str:
    digits = phone.lstrip("+")
    if len(digits) < 4:
        return phone
    return f"+{digits[0]} *** *** {digits[-4:]}"


async def delete_session(phone: str) -> bool:
    repo = AccountRepository()
    account = await repo.get_by_phone(phone)
    if not account:
        return False

    session_file = Path(settings.SESSIONS_DIR) / f"{account.id}.session"
    if session_file.exists():
        session_file.unlink()

    await repo.delete_by_phone(phone)
    return True
