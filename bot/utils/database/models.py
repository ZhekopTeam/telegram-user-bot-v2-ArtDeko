from datetime import datetime, timezone, date
from sqlalchemy import (
    BigInteger,
    Boolean,
    String,
    Integer,
    DateTime,
    Date,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    session_data: Mapped[str] = mapped_column(String, nullable=False)
    admin_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    proxy_type: Mapped[str] = mapped_column(String(16), nullable=False)
    host: Mapped[str] = mapped_column(String(256), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class WarmupGroup(Base):
    __tablename__ = "warmup_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    proxy_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("proxies.id", ondelete="SET NULL"),
        nullable=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="enabled", nullable=False)
    cycles_per_pair: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False)
    min_interval_min: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False)
    max_interval_min: Mapped[int] = mapped_column(
        Integer, default=15, nullable=False)
    day_start_hour: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False)
    day_end_hour: Mapped[int] = mapped_column(
        Integer, default=22, nullable=False)
    last_planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class WarmupGroupMember(Base):
    __tablename__ = "warmup_group_members"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("warmup_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("warmup_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    receiver_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pair_index: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_index: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
