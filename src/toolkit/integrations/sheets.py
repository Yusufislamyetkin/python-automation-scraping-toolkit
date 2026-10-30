"""Google Sheets: a `products` tab (full refresh), plus `changes` and `leads` tabs (append)."""

import asyncio
import csv
from pathlib import Path
from typing import Any, Protocol

from toolkit.logging import get_logger

log = get_logger(__name__)


class SheetsClient(Protocol):
    async def replace_rows(self, tab: str, header: list[str], rows: list[list[str]]) -> None: ...

    async def append_rows(self, tab: str, header: list[str], rows: list[list[str]]) -> None: ...


class GspreadSheetsClient:
    """Real client. Auth with a service account; share the sheet with its email."""

    def __init__(self, service_account_file: Path, sheet_id: str) -> None:
        import gspread

        self._gc = gspread.service_account(filename=str(service_account_file))
        self._sheet_id = sheet_id
        self._spreadsheet: Any = None

    def _worksheet(self, tab: str, header: list[str]) -> Any:
        import gspread

        if self._spreadsheet is None:
            self._spreadsheet = self._gc.open_by_key(self._sheet_id)
        try:
            ws = self._spreadsheet.worksheet(tab)
        except gspread.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(title=tab, rows=1000, cols=len(header))
            ws.append_row(header, value_input_option="RAW")
        return ws

    async def replace_rows(self, tab: str, header: list[str], rows: list[list[str]]) -> None:
        def _do() -> None:
            ws = self._worksheet(tab, header)
            ws.clear()
            ws.update([header, *rows], value_input_option="USER_ENTERED")

        await asyncio.to_thread(_do)
        log.info("sheets_replaced", tab=tab, rows=len(rows))

    async def append_rows(self, tab: str, header: list[str], rows: list[list[str]]) -> None:
        if not rows:
            return

        def _do() -> None:
            ws = self._worksheet(tab, header)
            ws.append_rows(rows, value_input_option="USER_ENTERED")

        await asyncio.to_thread(_do)
        log.info("sheets_appended", tab=tab, rows=len(rows))


class CsvSheetsClient:
    """Demo mode: one CSV per tab under `data/demo/`, same shape as the Sheet."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def _path(self, tab: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        return self._dir / f"sheet_{tab}.csv"

    async def replace_rows(self, tab: str, header: list[str], rows: list[list[str]]) -> None:
        path = self._path(tab)
        with path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows([header, *rows])
        log.info("would_send_sheets", mode="demo", tab=tab, rows=len(rows), file=str(path))

    async def append_rows(self, tab: str, header: list[str], rows: list[list[str]]) -> None:
        path = self._path(tab)
        new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if new:
                writer.writerow(header)
            writer.writerows(rows)
        log.info("would_send_sheets", mode="demo", tab=tab, rows=len(rows), file=str(path))


class FakeSheetsClient:
    """In-memory, for tests."""

    def __init__(self) -> None:
        self.tabs: dict[str, list[list[str]]] = {}

    async def replace_rows(self, tab: str, header: list[str], rows: list[list[str]]) -> None:
        self.tabs[tab] = [header, *rows]

    async def append_rows(self, tab: str, header: list[str], rows: list[list[str]]) -> None:
        self.tabs.setdefault(tab, [header]).extend(rows)
