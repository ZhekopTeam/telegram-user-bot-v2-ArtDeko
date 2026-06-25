import json
import os
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

venv = os.environ.get("VIRTUAL_ENV")
if venv:
    load_dotenv(dotenv_path=Path(venv) / ".env")


class Settings(BaseSettings):
    DB_ECHO: bool = Field(os.getenv("DB_ECHO", False))
    LOG_LEVEL: str = Field(os.getenv("LOG_LEVEL", "INFO"))
    LOG_FILE: str | None = Field(os.getenv("LOG_FILE", None))
    LOG_FORMAT: str = Field(
        os.getenv(
            "LOG_FORMAT",
            "%(levelname)-8s | %(asctime)s | %(message)s",
        )
    )
    LOG_DATE_FORMAT: str = Field(
        os.getenv(
            "LOG_DATE_FORMAT",
            "%H:%M:%S %d-%m-%Y",
        )
    )

    BOT_TOKEN: Optional[str] = Field(os.getenv("BOT_TOKEN", None))
    API_ID: Optional[int] = Field(os.getenv("API_ID", None))
    API_HASH: Optional[str] = Field(os.getenv("API_HASH", None))
    ADMINS: str = Field(os.getenv("ADMINS", ""))
    SESSION_MASTER_KEY: str = Field(
        os.getenv("SESSION_MASTER_KEY", "change-me-in-env"))

    SESSIONS_DIR: str = Field(os.getenv("SESSIONS_DIR", "/bot/sessions"))
    DATABASE_PATH: str = Field(
        os.getenv("DATABASE_PATH", "/bot/data/accounts.db"))

    SPREADSHEET_ID: str = Field(os.getenv("SPREADSHEET_ID", ""))
    SERVICE_ACCOUNT_PATH: str = Field(
        os.getenv("SERVICE_ACCOUNT_PATH", "/bot/data/service_account.json"))

    SCOPES: list[str] = Field(
        os.getenv("SCOPES", '["https://www.googleapis.com/auth/spreadsheets"]'))
    SHEET_ACCOUNTS: str = Field(
        os.getenv("SHEET_ACCOUNTS", "Telegram Accounts"))
    SHEET_COMMUNICATIONS: str = Field(
        os.getenv("SHEET_COMMUNICATIONS", "Telegram Communications"))
    ACCOUNTS_HEADER: list[str] = Field(os.getenv(
        "ACCOUNTS_HEADER", '["account_id", "phone", "username", "tg_id", "is_premium", "status", "created_at"]'))
    COMMS_HEADER: list[str] = Field(os.getenv(
        "COMMS_HEADER", '["group_id", "name", "accounts_chain", "start_date", "end_date", "status", "cycles_per_pair"]'))

    @field_validator("SCOPES", "ACCOUNTS_HEADER", "COMMS_HEADER", mode="before")
    @classmethod
    def _parse_list(cls, v: object) -> object:
        if isinstance(v, str):
            return json.loads(v)
        return v

    WARMUP_PLAN_HOUR: int = Field(int(os.getenv("WARMUP_PLAN_HOUR", 9)))
    WARMUP_PLAN_MINUTE: int = Field(int(os.getenv("WARMUP_PLAN_MINUTE", 0)))
    WARMUP_DISPATCH_INTERVAL_SEC: int = Field(
        int(os.getenv("WARMUP_DISPATCH_INTERVAL_SEC", 30)))
    WARMUP_CYCLES_PER_PAIR: int = Field(
        int(os.getenv("WARMUP_CYCLES_PER_PAIR", 3)))
    WARMUP_MIN_INTERVAL_MIN: int = Field(
        int(os.getenv("WARMUP_MIN_INTERVAL_MIN", 5)))
    WARMUP_MAX_INTERVAL_MIN: int = Field(
        int(os.getenv("WARMUP_MAX_INTERVAL_MIN", 15)))
    WARMUP_DAY_START_HOUR: int = Field(
        int(os.getenv("WARMUP_DAY_START_HOUR", 10)))
    WARMUP_DAY_END_HOUR: int = Field(
        int(os.getenv("WARMUP_DAY_END_HOUR", 22)))

    @property
    def admins_list(self) -> list[int]:
        return [int(i.strip()) for i in self.ADMINS.split(",") if i.strip()]


settings = Settings()

bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None

if settings.BOT_TOKEN:
    bot = Bot(settings.BOT_TOKEN,
              default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
