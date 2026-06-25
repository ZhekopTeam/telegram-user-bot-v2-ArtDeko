from sqlalchemy import select, delete as sa_delete, update as sa_update
from .db_engine import get_session_factory
from .models import Account


class AccountRepository:
    async def add(self, account: Account) -> None:
        async with get_session_factory()() as session:
            session.add(account)
            await session.commit()

    async def get_all(self) -> list[Account]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Account).order_by(Account.created_at)
            )
            return list(result.scalars().all())

    async def get_active(self) -> list[Account]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Account).where(Account.status ==
                                      "active").order_by(Account.created_at)
            )
            return list(result.scalars().all())

    async def get_by_id(self, account_id: str) -> Account | None:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Account).where(Account.id == account_id)
            )
            return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Account | None:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Account).where(Account.phone == phone)
            )
            return result.scalar_one_or_none()

    async def get_by_tg_id(self, tg_id: int) -> Account | None:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Account).where(Account.tg_id == tg_id)
            )
            return result.scalar_one_or_none()

    async def update_session_data(self, tg_id: int, session_data: str) -> None:
        async with get_session_factory()() as session:
            await session.execute(
                sa_update(Account)
                .where(Account.tg_id == tg_id)
                .values(session_data=session_data)
            )
            await session.commit()

    async def mark_revoked(self, tg_id: int) -> None:
        async with get_session_factory()() as session:
            await session.execute(
                sa_update(Account)
                .where(Account.tg_id == tg_id)
                .values(status="revoked")
            )
            await session.commit()

    async def reactivate(self, tg_id: int, session_data: str, admin_tg_id: int) -> None:
        async with get_session_factory()() as session:
            await session.execute(
                sa_update(Account)
                .where(Account.tg_id == tg_id)
                .values(session_data=session_data, status="active", admin_tg_id=admin_tg_id)
            )
            await session.commit()

    async def delete_by_phone(self, phone: str) -> bool:
        async with get_session_factory()() as session:
            result = await session.execute(
                sa_delete(Account).where(Account.phone == phone)
            )
            await session.commit()
            return result.rowcount > 0
