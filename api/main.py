"""InvoiceFlow REST API.

    uvicorn api.main:app --reload       # then open http://127.0.0.1:8000/docs

Environment variables:
    GOOGLE_API_KEY       Gemini key (without it, only the sample PDF layouts can be read)
    SHEETS_WEBHOOK_URL   Apps Script web app URL (integrations/google_apps_script.gs)
    SHEETS_TOKEN         the TOKEN set in that script
    APP_API_KEY          optional: callers must send it in the X-API-Key header
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from invoiceflow import (  # noqa: E402
    ExportError,
    ExportRegistry,
    Invoice,
    ParseResult,
    SheetWebhook,
    UnsupportedFile,
    check,
    export,
    make_reader,
    parse,
)
from invoiceflow.readers import MAX_FILE_BYTES  # noqa: E402

reader = make_reader()
registry = ExportRegistry(ROOT / ".cache" / "exported.json")
_url, _token = os.getenv("SHEETS_WEBHOOK_URL"), os.getenv("SHEETS_TOKEN")
sheet = SheetWebhook(_url, _token) if _url and _token else None
API_KEY = os.getenv("APP_API_KEY") or None

app = FastAPI(
    title="InvoiceFlow API",
    description="Read supplier invoices (PDF or photo), check the GST arithmetic, and send them to Google Sheets.",
    version="1.0",
)


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or wrong X-API-Key header")


class ExportRequest(BaseModel):
    invoice: Invoice
    source: str = ""
    force: bool = False


@app.get("/health")
def health() -> dict:
    return {"ok": True, "reader": reader.name, "google_sheet": sheet is not None}


@app.post("/invoices/parse", response_model=ParseResult, dependencies=[Depends(require_key)])
def parse_invoice(file: UploadFile = File(...)) -> ParseResult:
    """Upload a PDF, PNG, JPG or WEBP invoice. Returns the data and every check, with a status:
    ready (all checks passed), check (warnings) or blocked (errors)."""
    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB")
    try:
        return parse(data, file.filename or "upload", reader, registry)
    except UnsupportedFile as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        text = f"{type(error).__name__} {error}".lower()
        if any(s in text for s in ("429", "resource_exhausted", "quota", "rate limit")):
            raise HTTPException(status_code=503, detail="The AI service is busy. Try again in a minute.") from error
        raise HTTPException(status_code=502, detail=f"Could not read the invoice ({type(error).__name__})") from error


@app.post("/invoices/check", response_model=ParseResult, dependencies=[Depends(require_key)])
def check_invoice(body: ExportRequest) -> ParseResult:
    """Re-run the checks on invoice data, for example after a person corrected a value."""
    return check(body.invoice, body.source, "edited", registry)


@app.post("/invoices/export", dependencies=[Depends(require_key)])
def export_invoice(body: ExportRequest) -> dict:
    """Send a checked invoice to the Google Sheet ("Invoices" and "Line items" tabs).
    Invoices with errors need force=true; duplicates are always refused."""
    result = check(body.invoice, body.source, "edited", registry)
    try:
        rows = export(result, sheet, registry, force=body.force)
    except ExportError as error:
        message = str(error)
        status = 409 if "already" in message else 503 if "No Google Sheet" in message else 422
        raise HTTPException(status_code=status, detail=message) from error
    return {"exported": True, "rows_added": rows, "status": result.status}
