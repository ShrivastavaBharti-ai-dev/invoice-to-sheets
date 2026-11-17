"""Turn checked invoices into spreadsheet rows: a Google Sheet (via the Apps
Script webhook in integrations/), a CSV download, and duplicate protection."""
from __future__ import annotations

import csv
import io
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import gstin as G
from .models import ParseResult

INVOICE_HEADER = ["Received", "Supplier", "Supplier GSTIN", "Invoice no", "Invoice date", "Subtotal", "CGST",
                  "SGST", "IGST", "Round off", "Total", "Status", "Issues", "File"]
ITEM_HEADER = ["Supplier", "Invoice no", "Invoice date", "Description", "HSN", "Qty", "Unit", "Rate", "Amount"]


def invoice_row(result: ParseResult) -> list:
    inv = result.invoice
    issues = "; ".join(f"{c.name}: {c.message}" for c in result.problems)
    return [datetime.now().isoformat(timespec="seconds"), inv.supplier_name, G.clean(inv.supplier_gstin),
            inv.invoice_number, inv.invoice_date, inv.subtotal, inv.cgst, inv.sgst, inv.igst, inv.round_off,
            inv.total, result.status.upper(), issues, result.source]


def item_rows(result: ParseResult) -> list[list]:
    inv = result.invoice
    return [[inv.supplier_name, inv.invoice_number, inv.invoice_date, item.description, item.hsn, item.quantity,
             item.unit, item.rate, item.amount] for item in inv.line_items]


def to_csv(results: list[ParseResult]) -> bytes:
    """One row per line item, with the invoice details repeated. Opens in Excel and Google Sheets."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(ITEM_HEADER + ["Invoice total", "Status"])
    for result in results:
        for row in item_rows(result):
            writer.writerow(row + [result.invoice.total, result.status.upper()])
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM so Excel shows ₹ and accents correctly


def duplicate_key(result: ParseResult) -> str:
    inv = result.invoice
    return f"{G.clean(inv.supplier_gstin) or inv.supplier_name.lower()}|{inv.invoice_number.upper()}"


class ExportRegistry:
    """Remembers which invoices were already sent, so the same bill is never entered twice."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._keys: set[str] = set()
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            try:
                self._keys = set(json.loads(self.path.read_text()))
            except (OSError, json.JSONDecodeError):
                self._keys = set()

    def seen(self, result: ParseResult) -> bool:
        return duplicate_key(result) in self._keys

    def remember(self, result: ParseResult) -> None:
        with self._lock:
            self._keys.add(duplicate_key(result))
            if self.path:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self.path.write_text(json.dumps(sorted(self._keys)))
                except OSError:
                    self.path = None


class ExportError(RuntimeError):
    pass


class SheetWebhook:
    """POST rows to the Apps Script web app (integrations/google_apps_script.gs)."""

    def __init__(self, url: str, token: str, timeout: float = 20.0):
        self.url, self.token, self.timeout = url, token, timeout

    def append(self, tab: str, header: list, rows: list[list]) -> None:
        payload = {"token": self.token, "tab": tab, "header": header, "rows": rows, "notify": None}
        request = urllib.request.Request(self.url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as error:
            raise ExportError(f"Could not reach the Google Sheet: {error}") from error
        try:
            answer = json.loads(body)
        except json.JSONDecodeError as error:
            raise ExportError(f"Unexpected reply from the Google Sheet: {body[:200]}") from error
        if not answer.get("ok"):
            raise ExportError(f"The Google Sheet refused the rows: {answer.get('error', 'unknown error')}")

    def export(self, result: ParseResult) -> int:
        self.append("Invoices", INVOICE_HEADER, [invoice_row(result)])
        items = item_rows(result)
        if items:
            self.append("Line items", ITEM_HEADER, items)
        return 1 + len(items)
