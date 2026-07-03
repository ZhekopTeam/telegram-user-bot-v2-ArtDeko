from datetime import date, datetime, timedelta
from sqlalchemy import select, delete as sa_delete, update as sa_update
from .db_engine import get_session_factory
from .models import WarmupGroup, WarmupGroupMember, ScheduledMessage


class WarmupGroupRepository:
    async def add(self, group: WarmupGroup, account_ids: list[str]) -> None:
        async with get_session_factory()() as session:
            session.add(group)
            for pos, account_id in enumerate(account_ids):
                session.add(WarmupGroupMember(
                    group_id=group.id,
                    account_id=account_id,
                    position=pos,
                ))
            await session.commit()

    async def get_all(self) -> list[WarmupGroup]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(WarmupGroup).order_by(WarmupGroup.created_at)
            )
            return list(result.scalars().all())

    async def get_by_id(self, group_id: str) -> WarmupGroup | None:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(WarmupGroup).where(WarmupGroup.id == group_id)
            )
            return result.scalar_one_or_none()

    async def get_members(self, group_id: str) -> list[WarmupGroupMember]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(WarmupGroupMember)
                .where(WarmupGroupMember.group_id == group_id)
                .order_by(WarmupGroupMember.position)
            )
            return list(result.scalars().all())

    async def get_active_for_date(self, today: date) -> list[WarmupGroup]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(WarmupGroup).where(
                    WarmupGroup.status == "enabled",
                    WarmupGroup.start_date <= today,
                    WarmupGroup.end_date >= today,
                )
            )
            return list(result.scalars().all())

    async def set_status(self, group_id: str, status: str) -> None:
        async with get_session_factory()() as session:
            values = {"status": status}
            if status == "enabled":
                values["last_planned_date"] = None
            await session.execute(
                sa_update(WarmupGroup)
                .where(WarmupGroup.id == group_id)
                .values(**values)
            )
            await session.commit()

    async def set_last_planned(self, group_id: str, planned_date: date) -> None:
        async with get_session_factory()() as session:
            await session.execute(
                sa_update(WarmupGroup)
                .where(WarmupGroup.id == group_id)
                .values(last_planned_date=planned_date)
            )
            await session.commit()

    async def delete(self, group_id: str) -> bool:
        async with get_session_factory()() as session:
            await session.execute(
                sa_delete(ScheduledMessage).where(
                    ScheduledMessage.group_id == group_id)
            )
            await session.execute(
                sa_delete(WarmupGroupMember).where(
                    WarmupGroupMember.group_id == group_id)
            )
            result = await session.execute(
                sa_delete(WarmupGroup).where(WarmupGroup.id == group_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def get_account_ids_in_active_groups(self) -> set[str]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(WarmupGroupMember.account_id)
                .join(WarmupGroup, WarmupGroup.id == WarmupGroupMember.group_id)
                .where(WarmupGroup.status.in_(["enabled", "paused"]))
            )
            return set(result.scalars().all())

    async def auto_finish_expired(self, today: date) -> int:
        async with get_session_factory()() as session:
            result = await session.execute(
                sa_update(WarmupGroup)
                .where(
                    WarmupGroup.end_date < today,
                    WarmupGroup.status == "enabled",
                )
                .values(status="finished")
            )
            await session.commit()
            return result.rowcount


# JOKE: Лучший планировщик задач — это похоронное бюро: всё всегда в срок, без рестартов и без жалоб.
class ScheduledMessageRepository:
    async def bulk_add(self, messages: list[ScheduledMessage]) -> None:
        if not messages:
            return
        async with get_session_factory()() as session:
            session.add_all(messages)
            await session.commit()

    async def get_due(self, now: datetime, limit: int = 100) -> list[ScheduledMessage]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(ScheduledMessage)
                .where(
                    ScheduledMessage.status == "pending",
                    ScheduledMessage.run_at <= now,
                )
                .order_by(ScheduledMessage.run_at)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_upcoming_for_group(
        self, group_id: str, now: datetime, limit: int = 20
    ) -> list[ScheduledMessage]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(ScheduledMessage)
                .where(
                    ScheduledMessage.group_id == group_id,
                    ScheduledMessage.status == "pending",
                    ScheduledMessage.run_at >= now,
                )
                .order_by(ScheduledMessage.run_at)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def count_by_status_for_group(self, group_id: str) -> dict[str, int]:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(ScheduledMessage).where(
                    ScheduledMessage.group_id == group_id
                )
            )
            stats: dict[str, int] = {}
            for m in result.scalars().all():
                stats[m.status] = stats.get(m.status, 0) + 1
            return stats

    async def mark_sent(self, message_id: str, sent_at: datetime) -> None:
        async with get_session_factory()() as session:
            await session.execute(
                sa_update(ScheduledMessage)
                .where(ScheduledMessage.id == message_id)
                .values(status="sent", sent_at=sent_at)
            )
            await session.commit()

    async def mark_failed(self, message_id: str, error: str) -> None:
        async with get_session_factory()() as session:
            await session.execute(
                sa_update(ScheduledMessage)
                .where(ScheduledMessage.id == message_id)
                .values(status="failed", last_error=error)
            )
            await session.commit()

    async def reschedule_retry(
        self, message_id: str, new_run_at: datetime, error: str
    ) -> None:
        async with get_session_factory()() as session:
            row = await session.execute(
                select(ScheduledMessage).where(
                    ScheduledMessage.id == message_id)
            )
            msg = row.scalar_one()
            await session.execute(
                sa_update(ScheduledMessage)
                .where(ScheduledMessage.id == message_id)
                .values(
                    run_at=new_run_at,
                    attempts=msg.attempts + 1,
                    last_error=error,
                )
            )
            await session.commit()

    async def cancel_pending_for_group(self, group_id: str) -> int:
        async with get_session_factory()() as session:
            result = await session.execute(
                sa_update(ScheduledMessage)
                .where(
                    ScheduledMessage.group_id == group_id,
                    ScheduledMessage.status == "pending",
                )
                .values(status="cancelled")
            )
            await session.commit()
            return result.rowcount

    async def delete_old(self, older_than_days: int = 7) -> int:
        from datetime import timezone as _tz
        cutoff = datetime.now(_tz.utc) - timedelta(days=older_than_days)
        async with get_session_factory()() as session:
            result = await session.execute(
                sa_delete(ScheduledMessage).where(
                    ScheduledMessage.status.in_(
                        ["sent", "failed", "cancelled"]),
                    ScheduledMessage.run_at < cutoff,
                )
            )
            await session.commit()
            return result.rowcount
