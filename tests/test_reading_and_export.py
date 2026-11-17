"""Reading the sample files without a key, CSV export, duplicates and the Google Sheet webhook."""
import csv
import io
import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from invoiceflow import (ExportError, ExportRegistry, Invoice, SheetWebhook, TextRulesReader, UnsupportedFile,
                         export, parse, to_csv)
from invoiceflow.readers import mime_type

ROOT = Path(__file__).resolve().parent.parent
KEY = json.loads((ROOT / "samples" / "answer_key.json").read_text(encoding="utf-8"))
PDFS = [name for name in KEY if name.endswith(".pdf")]


def read(name, registry=None):
    return parse((ROOT / "samples" / name).read_bytes(), name, TextRulesReader(), registry, today=date(2026, 11, 14))


@pytest.mark.parametrize("name", PDFS)
def test_text_reader_matches_answer_key(name):
    result = read(name)
    expected = Invoice.model_validate(KEY[name]["invoice"])
    assert result.invoice.model_dump() == expected.model_dump()
    assert result.status == KEY[name]["expected_status"]


def test_photo_needs_gemini():
    with pytest.raises(UnsupportedFile, match="Gemini"):
        read("06_indore_bakery_photo.jpg")


def test_file_type_comes_from_content_not_name():
    pdf = (ROOT / "samples" / PDFS[0]).read_bytes()
    assert mime_type(pdf, "renamed.jpg") == "application/pdf"
    with pytest.raises(UnsupportedFile):
        mime_type(b"MZ\x90\x00 not an invoice", "invoice.pdf")
    with pytest.raises(UnsupportedFile, match="empty"):
        TextRulesReader().read(b"", "x.pdf")


def test_csv_has_one_row_per_line_item():
    results = [read(PDFS[0]), read(PDFS[1])]
    text = to_csv(results).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][:3] == ["Supplier", "Invoice no", "Invoice date"]
    assert len(rows) == 1 + 3 + 5 and rows[1][0] == "Narmada Dairy Suppliers"


class FakeAppsScript(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        FakeAppsScript.received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(302)
        self.send_header("Location", "/done")
        self.end_headers()

    def do_GET(self):
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def sheet():
    server = HTTPServer(("127.0.0.1", 0), FakeAppsScript)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    FakeAppsScript.received.clear()
    yield SheetWebhook(f"http://127.0.0.1:{server.server_port}/exec", "secret")
    server.shutdown()


def test_export_writes_two_tabs_once(sheet, tmp_path):
    registry = ExportRegistry(tmp_path / "exported.json")
    result = read(PDFS[0], registry)
    assert export(result, sheet, registry) == 4
    tabs = [p["tab"] for p in FakeAppsScript.received]
    assert tabs == ["Invoices", "Line items"] and FakeAppsScript.received[0]["token"] == "secret"
    with pytest.raises(ExportError, match="already"):
        export(result, sheet, registry)
    again = read(PDFS[0], ExportRegistry(tmp_path / "exported.json"))   # remembered on disk
    assert again.status == "blocked" and any(c.name == "Duplicate" for c in again.problems)


def test_blocked_invoice_needs_confirmation(sheet):
    registry = ExportRegistry()
    result = read("05_cleanpro_with_error.pdf", registry)
    with pytest.raises(ExportError, match="errors"):
        export(result, sheet, registry)
    assert export(result, sheet, registry, force=True) == 5


def test_no_sheet_configured():
    with pytest.raises(ExportError, match="No Google Sheet"):
        export(read(PDFS[1]), None, ExportRegistry())
