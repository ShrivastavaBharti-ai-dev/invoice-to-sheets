"""Turn an invoice file (PDF or photo) into an Invoice.

* GeminiReader: sends the PDF or image to Gemini (via LangChain) and asks for
  structured JSON. Works with any layout, scans and phone photos.
* TextRulesReader: no API key needed. Reads the text layer of the sample PDFs
  with simple rules. It only understands the layouts in samples/.
"""
from __future__ import annotations

import base64
import os
import re
import time
from io import BytesIO

from .models import Invoice, LineItem

DEFAULT_CHAT_MODEL = "gemini-3.5-flash-lite"
MAX_FILE_BYTES = 10 * 1024 * 1024
MIME_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp"}


class UnsupportedFile(ValueError):
    pass


def mime_type(data: bytes, filename: str) -> str:
    """Trust the file's first bytes over its name."""
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    ext = os.path.splitext(filename.lower())[1]
    raise UnsupportedFile(f"{filename}: please upload a PDF, PNG, JPG or WEBP file" +
                          (" (the file content doesn't match its name)" if ext in MIME_TYPES else ""))


def check_size(data: bytes) -> None:
    if not data:
        raise UnsupportedFile("The file is empty")
    if len(data) > MAX_FILE_BYTES:
        raise UnsupportedFile("The file is larger than 10 MB")


# ------------------------------------------------------------------ Gemini
INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "supplier_name": {"type": "string"},
        "supplier_gstin": {"type": "string"},
        "buyer_name": {"type": "string"},
        "buyer_gstin": {"type": "string"},
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": "string", "description": "YYYY-MM-DD"},
        "place_of_supply": {"type": "string"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "hsn": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "rate": {"type": "number"},
                    "amount": {"type": "number"},
                },
                "required": ["description", "hsn", "quantity", "unit", "rate", "amount"],
            },
        },
        "subtotal": {"type": "number"},
        "cgst": {"type": "number"},
        "sgst": {"type": "number"},
        "igst": {"type": "number"},
        "round_off": {"type": "number"},
        "total": {"type": "number"},
        "unreadable_fields": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["supplier_name", "supplier_gstin", "buyer_name", "buyer_gstin", "invoice_number", "invoice_date",
                 "place_of_supply", "line_items", "subtotal", "cgst", "sgst", "igst", "round_off", "total",
                 "unreadable_fields"],
}

PROMPT = """Extract the data from this Indian GST tax invoice.
Rules:
- Copy exactly what is printed. Do NOT calculate, fix or complete anything: if a printed amount or total looks wrong,
  still copy the printed value. Our software checks the arithmetic separately.
- Dates on Indian invoices are DD/MM/YYYY; return them as YYYY-MM-DD.
- Amounts as plain numbers without currency symbols or commas. Use 0 for taxes that are not on the invoice.
- The supplier is the business that issued the invoice; the buyer is under "Bill to" / "Buyer".
- Use "" for text that is not on the invoice. Never invent a GSTIN, invoice number or date.
- In unreadable_fields, list the names of any fields you could not read with confidence (blurred, cut off, handwritten)."""


class GeminiReader:
    live = True

    def __init__(self, model: str | None = None):
        from langchain_google_genai import ChatGoogleGenerativeAI

        self.model = model or os.getenv("GEMINI_CHAT_MODEL", DEFAULT_CHAT_MODEL)
        self.name = f"gemini:{self.model}"
        llm = ChatGoogleGenerativeAI(model=self.model, max_retries=2)
        self._chain = llm.with_structured_output(INVOICE_SCHEMA, method="json_schema")

    def read(self, data: bytes, filename: str) -> Invoice:
        from langchain_core.messages import HumanMessage

        check_size(data)
        mime = mime_type(data, filename)
        encoded = base64.b64encode(data).decode("ascii")
        block = ({"type": "file", "base64": encoded, "mime_type": mime} if mime == "application/pdf"
                 else {"type": "image", "base64": encoded, "mime_type": mime})
        message = HumanMessage(content=[{"type": "text", "text": PROMPT}, block])
        raw = _with_backoff(lambda: self._chain.invoke([message]))
        if not isinstance(raw, dict):
            raise ValueError("The model did not return invoice data")
        return Invoice.model_validate(raw)


def _with_backoff(call, retries: int = 3, base_delay: float = 3.0):
    for attempt in range(retries + 1):
        try:
            return call()
        except Exception as error:  # noqa: BLE001
            text = f"{type(error).__name__} {error}".lower()
            if attempt == retries or not any(s in text for s in ("429", "resource_exhausted", "quota", "rate limit")):
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise RuntimeError("unreachable")


# ------------------------------------------------------------------ offline
_NUMBER = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
_TOTAL_LABELS = {"subtotal": "subtotal", "cgst": "cgst", "sgst": "sgst", "igst": "igst", "round off": "round_off",
                 "grand total": "total"}


def _num(text: str) -> float:
    return float(text.replace("₹", "").replace("Rs.", "").replace(",", "").strip())


def _iso(ddmmyyyy: str) -> str:
    match = re.match(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", ddmmyyyy.strip())
    return f"{match.group(3)}-{int(match.group(2)):02d}-{int(match.group(1)):02d}" if match else ddmmyyyy.strip()


class TextRulesReader:
    """Reads the text layer of the sample invoice layouts. No API key needed."""

    name = "text-rules"
    live = False

    def read(self, data: bytes, filename: str) -> Invoice:
        from pypdf import PdfReader

        check_size(data)
        if mime_type(data, filename) != "application/pdf":
            raise UnsupportedFile("Photos need Gemini. Add a GOOGLE_API_KEY to read images.")
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise UnsupportedFile("No text found: this looks like a scanned PDF, which needs Gemini")

        def after(label: str, nth: int = 0) -> str:
            hits = [line.split(":", 1)[1].strip() for line in lines if line.lower().startswith(label.lower() + ":")]
            return hits[nth] if len(hits) > nth else ""

        inv: dict = {"supplier_name": lines[0], "supplier_gstin": after("GSTIN"), "buyer_gstin": after("GSTIN", 1),
                     "invoice_number": after("Invoice No"), "invoice_date": _iso(after("Invoice Date")),
                     "place_of_supply": re.sub(r"\s*\(\d+\)$", "", after("Place of Supply"))}
        if "Bill To:" in lines:
            inv["buyer_name"] = lines[lines.index("Bill To:") + 1]

        items: list[LineItem] = []
        start = next((i + 1 for i, line in enumerate(lines) if line.startswith("Amount")), None)
        i = start or len(lines)
        while i + 6 < len(lines) and lines[i] == str(len(items) + 1):
            n, desc, hsn, qty, unit, rate, amount = lines[i:i + 7]
            items.append(LineItem(description=desc, hsn=hsn, quantity=_num(qty), unit=unit, rate=_num(rate),
                                  amount=_num(amount)))
            i += 7
        inv["line_items"] = items
        while i + 1 < len(lines):
            key = _TOTAL_LABELS.get(lines[i].lower())
            value = lines[i + 1].replace("₹", "").strip()
            if key and _NUMBER.match(value):
                inv[key] = _num(value)
                i += 2
            else:
                i += 1
        return Invoice.model_validate(inv)


def make_reader(api_key: str | None = None):
    key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if key:
        os.environ["GOOGLE_API_KEY"] = key
        return GeminiReader()
    return TextRulesReader()
