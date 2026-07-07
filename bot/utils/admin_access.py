from config import settings
from utils.logger import logger

_bootstrap_admins: set[int] = set(settings.admins_list)
_db_admins: set[int] = set()


def _bootstrap_ids() -> set[int]:
    return set(settings.admins_list)


async def load_db_admins() -> None:
    global _bootstrap_admins, _db_admins
    _bootstrap_admins = _bootstrap_ids()
    from utils.database.admin_repo import AdminRepository
    _db_admins = set(await AdminRepository().get_all_tg_ids())
    logger.info(
        f"Admins loaded: bootstrap={sorted(_bootstrap_admins)}, "
        f"db={sorted(_db_admins)}"
    )


def owner_ids() -> list[int]:
    """Владельцы — все Telegram ID из ADMINS в .env."""
    return sorted(_bootstrap_admins)


def is_owner(tg_id: int) -> bool:
    return tg_id in _bootstrap_admins


def is_admin(tg_id: int) -> bool:
    return tg_id in _bootstrap_admins or tg_id in _db_admins


def all_admin_ids() -> list[int]:
    return sorted(_bootstrap_admins | _db_admins)


def bootstrap_admin_ids() -> list[int]:
    return sorted(_bootstrap_admins)


def db_admin_ids() -> list[int]:
    return sorted(_db_admins)


async def add_admin(tg_id: int) -> None:
    from utils.database.admin_repo import AdminRepository
    await AdminRepository().add(tg_id)
    _db_admins.add(tg_id)


async def remove_admin(tg_id: int) -> bool:
    if tg_id in _bootstrap_admins:
        return False
    from utils.database.admin_repo import AdminRepository
    removed = await AdminRepository().delete(tg_id)
    if removed:
        _db_admins.discard(tg_id)
    return removed
