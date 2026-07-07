from sqlalchemy import select, delete as sa_delete
from .db_engine import get_session_factory
from .models import BotAdmin


class AdminRepository:
    async def get_all_tg_ids(self) -> list[int]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(BotAdmin.tg_id).order_by(BotAdmin.tg_id)
            )
            return list(result.scalars().all())

    async def add(self, tg_id: int) -> None:
        async with get_session_factory()() as session:
            existing = await session.get(BotAdmin, tg_id)
            if existing is None:
                session.add(BotAdmin(tg_id=tg_id))
                await session.commit()

    async def delete(self, tg_id: int) -> bool:
        async with get_session_factory()() as session:
            result = await session.execute(
                sa_delete(BotAdmin).where(BotAdmin.tg_id == tg_id)
            )
            await session.commit()
            return result.rowcount > 0
