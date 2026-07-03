import random
from uuid import uuid4
from datetime import datetime, date, time, timezone, timedelta

from utils.logger import logger
from utils.database import (
    WarmupGroup,
    WarmupGroupRepository,
    ScheduledMessage,
    ScheduledMessageRepository,
)


class WarmupPlanner:
    def __init__(self) -> None:
        self._groups = WarmupGroupRepository()
        self._messages = ScheduledMessageRepository()

    async def plan_today_for_all(self, today: date) -> int:
        await self._groups.auto_finish_expired(today)
        groups = await self._groups.get_active_for_date(today)
        planned = 0
        for group in groups:
            if group.last_planned_date == today:
                continue
            ok = await self.plan_day(group, today)
            if ok:
                planned += 1
        return planned

    async def plan_day(self, group: WarmupGroup, day: date) -> bool:
        members = await self._groups.get_members(group.id)
        if len(members) < 2:
            logger.warning(
                f"Group {group.id} has less than 2 members, skip planning")
            return False

        now_utc = datetime.now(timezone.utc)
        day_start_local = datetime.combine(
            day, time(hour=group.day_start_hour))
        day_end_local = datetime.combine(
            day, time(hour=group.day_end_hour))

        cursor = day_start_local.astimezone(timezone.utc)
        if cursor < now_utc:
            cursor = now_utc + timedelta(seconds=30)

        end_utc = day_end_local.astimezone(timezone.utc)

        pairs = [
            (members[i].account_id, members[(i + 1) % len(members)].account_id)
            for i in range(len(members))
        ]

        messages: list[ScheduledMessage] = []
        for pair_idx, (sender_id, receiver_id) in enumerate(pairs):
            for cycle in range(group.cycles_per_pair):
                if cursor >= end_utc:
                    logger.warning(
                        f"Group {group.id}: day window exhausted at "
                        f"pair {pair_idx} cycle {cycle}"
                    )
                    break

                messages.append(self._build_msg(
                    group.id, sender_id, receiver_id,
                    cursor, pair_idx, cycle, "forward",
                ))
                cursor += timedelta(minutes=random.randint(
                    group.min_interval_min, group.max_interval_min))

                if cursor >= end_utc:
                    break

                messages.append(self._build_msg(
                    group.id, receiver_id, sender_id,
                    cursor, pair_idx, cycle, "reply",
                ))
                cursor += timedelta(minutes=random.randint(
                    group.min_interval_min, group.max_interval_min))

        if not messages:
            return False

        await self._messages.bulk_add(messages)
        await self._groups.set_last_planned(group.id, day)
        logger.info(
            f"Planned {len(messages)} messages for group {group.id} on {day}"
        )
        return True

    @staticmethod
    def _build_msg(
        group_id: str,
        sender_id: str,
        receiver_id: str,
        run_at: datetime,
        pair_idx: int,
        cycle_idx: int,
        direction: str,
    ) -> ScheduledMessage:
        return ScheduledMessage(
            id=str(uuid4()),
            group_id=group_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            run_at=run_at,
            status="pending",
            attempts=0,
            pair_index=pair_idx,
            cycle_index=cycle_idx,
            direction=direction,
        )
