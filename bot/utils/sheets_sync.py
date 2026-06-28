import asyncio
from functools import partial
from pathlib import Path
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from config import settings
from utils.logger import logger


def _get_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(
        settings.SERVICE_ACCOUNT_PATH, scopes=settings.SCOPES
    )
    return gspread.authorize(creds)


def _ensure_sheet(spreadsheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=1000, cols=20)


def _write_sheet(ws: gspread.Worksheet, header: list[str], rows: list[list[Any]]) -> None:
    ws.clear()
    data = [header] + rows
    ws.update(range_name="A1", values=data)
    ws.format("A1:Z1", {"textFormat": {"bold": True}})


def _sync_accounts_blocking() -> None:
    from utils.database import AccountRepository
    import asyncio as _asyncio

    accounts = _asyncio.run(AccountRepository().get_all())
    rows = [
        [
            str(a.id),
            a.phone,
            a.username or "",
            str(a.tg_id),
            "Да" if a.is_premium else "Нет",
            a.status,
            a.created_at.strftime("%d.%m.%Y %H:%M") if a.created_at else "",
        ]
        for a in accounts
    ]
    gc = _get_client()
    ss = gc.open_by_key(settings.SPREADSHEET_ID)
    ws = _ensure_sheet(ss, settings.SHEET_ACCOUNTS)
    _write_sheet(ws, settings.ACCOUNTS_HEADER, rows)
    logger.info(f"Sheets: synced {len(rows)} accounts")


def _sync_warmup_blocking() -> None:
    from utils.database import WarmupGroupRepository, AccountRepository
    import asyncio as _asyncio

    group_repo = WarmupGroupRepository()
    acc_repo = AccountRepository()

    groups = _asyncio.run(group_repo.get_all())
    all_accounts = {a.id: a for a in _asyncio.run(acc_repo.get_all())}

    rows = []
    for g in groups:
        members = _asyncio.run(group_repo.get_members(g.id))
        chain = " → ".join(
            all_accounts[m.account_id].phone
            if m.account_id in all_accounts else "?"
            for m in members
        )
        rows.append([
            str(g.id[:8]),
            g.name,
            chain,
            g.start_date.strftime("%d.%m.%Y"),
            g.end_date.strftime("%d.%m.%Y"),
            g.status,
            str(g.cycles_per_pair),
        ])

    gc = _get_client()
    ss = gc.open_by_key(settings.SPREADSHEET_ID)
    ws = _ensure_sheet(ss, settings.SHEET_COMMUNICATIONS)
    _write_sheet(ws, settings.COMMS_HEADER, rows)
    logger.info(f"Sheets: synced {len(rows)} warmup groups")


async def _run_blocking(fn) -> None:
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, fn)
    except Exception as e:
        logger.warning(f"Google Sheets sync failed: {type(e).__name__}: {e}")


def _sheets_enabled() -> bool:
    if not settings.SPREADSHEET_ID or not settings.SERVICE_ACCOUNT_PATH:
        return False
    if not Path(settings.SERVICE_ACCOUNT_PATH).exists():
        return False
    return True


class SheetsSync:
    @classmethod
    async def sync_accounts(cls) -> None:
        if not _sheets_enabled():
            return
        await _run_blocking(_sync_accounts_blocking)

    @classmethod
    async def sync_warmup(cls) -> None:
        if not _sheets_enabled():
            return
        await _run_blocking(_sync_warmup_blocking)
