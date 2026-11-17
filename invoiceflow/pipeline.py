"""Read -> validate -> (export). Shared by the API and the Streamlit demo."""
from __future__ import annotations

from datetime import date

from .export import ExportError, ExportRegistry, SheetWebhook
from .models import Invoice, ParseResult
from .validate import validate


def check(invoice: Invoice, source: str, reader_name: str, registry: ExportRegistry | None = None,
          today: date | None = None) -> ParseResult:
    draft = ParseResult(invoice=invoice, checks=[], status="ready", source=source, reader=reader_name)
    duplicate = bool(registry and registry.seen(draft))
    checks, status = validate(invoice, today=today, already_exported=duplicate)
    return ParseResult(invoice=invoice, checks=checks, status=status, source=source, reader=reader_name)


def parse(data: bytes, filename: str, reader, registry: ExportRegistry | None = None,
          today: date | None = None) -> ParseResult:
    invoice = reader.read(data, filename)
    return check(invoice, filename, reader.name, registry, today)


def export(result: ParseResult, sheet: SheetWebhook | None, registry: ExportRegistry, force: bool = False) -> int:
    """Send to the sheet. Blocked invoices need force=True (someone looked at them)."""
    if registry.seen(result):
        raise ExportError("This invoice was already sent to the sheet")
    if result.status == "blocked" and not force:
        raise ExportError("This invoice has errors. Fix them, or confirm you want to send it anyway")
    if sheet is None:
        raise ExportError("No Google Sheet is set up (SHEETS_WEBHOOK_URL and SHEETS_TOKEN)")
    rows = sheet.export(result)
    registry.remember(result)
    return rows
