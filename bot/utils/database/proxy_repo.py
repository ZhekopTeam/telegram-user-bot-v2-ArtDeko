from sqlalchemy import select, delete as sa_delete
from .db_engine import get_session_factory
from .models import Proxy


class ProxyRepository:
    async def add(self, proxy: Proxy) -> None:
        async with get_session_factory()() as session:
            session.add(proxy)
            await session.commit()

    async def get_all(self) -> list[Proxy]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Proxy).order_by(Proxy.created_at)
            )
            return list(result.scalars().all())

    async def get_by_id(self, proxy_id: str) -> Proxy | None:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Proxy).where(Proxy.id == proxy_id)
            )
            return result.scalar_one_or_none()

    async def delete(self, proxy_id: str) -> bool:
        async with get_session_factory()() as session:
            result = await session.execute(
                sa_delete(Proxy).where(Proxy.id == proxy_id)
            )
            await session.commit()
            return result.rowcount > 0
