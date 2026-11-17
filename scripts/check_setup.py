"""Check packages, the Gemini key and (if set up) the Google Sheet webhook.

    python scripts/check_setup.py

Reads one sample photo with Gemini, and adds one test row to a "Setup test"
tab in your Google Sheet if SHEETS_WEBHOOK_URL is set.
"""
from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
problems = 0


def report(ok: bool, message: str, hint: str = "") -> None:
    global problems
    print(f"{'[ OK ]' if ok else '[FAIL]'} {message}")
    if not ok:
        problems += 1
        if hint:
            print(f"       -> {hint}")


report(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "Install Python 3.10 or newer (3.12 recommended).")
for module, package in [("fastapi", "fastapi"), ("multipart", "python-multipart"), ("streamlit", "streamlit"),
                        ("langchain_core", "langchain-core"), ("langchain_google_genai", "langchain-google-genai"),
                        ("pypdf", "pypdf"), ("pandas", "pandas"), ("dotenv", "python-dotenv")]:
    try:
        version = getattr(importlib.import_module(module), "__version__", "")
        report(True, f"{package} {version}".strip())
    except ImportError:
        report(False, f"{package} is not installed", "Run: pip install -r requirements.txt")

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
report(bool(key), f"GOOGLE_API_KEY found (ends in ...{key[-4:]})" if key else "GOOGLE_API_KEY is missing",
       "Copy .env.example to .env and paste your key from https://aistudio.google.com/apikey")

if key and problems == 0:
    from invoiceflow import make_reader, parse
    try:
        name = "06_indore_bakery_photo.jpg"
        result = parse((ROOT / "samples" / name).read_bytes(), name, make_reader(key))
        report(result.invoice.invoice_number.upper() == "IBI/26/3310",
               f"Gemini read the sample photo: invoice {result.invoice.invoice_number}, total "
               f"₹{result.invoice.total:,.2f}, status {result.status}",
               "Gemini read the photo but got the invoice number wrong; try GEMINI_CHAT_MODEL=gemini-3.6-flash")
    except Exception as error:  # noqa: BLE001
        report(False, f"Gemini call failed: {type(error).__name__}: {str(error)[:300]}",
               "Check the key. If the model is not found, set GEMINI_CHAT_MODEL in .env (e.g. gemini-3.1-flash-lite).")

url, token = os.getenv("SHEETS_WEBHOOK_URL"), os.getenv("SHEETS_TOKEN")
if url and token:
    from invoiceflow import SheetWebhook
    try:
        SheetWebhook(url, token).append("Setup test", ["Time", "Check"],
                                        [[datetime.now().isoformat(timespec="seconds"), "InvoiceFlow works"]])
        report(True, "Google Sheet webhook works: a row was added to the 'Setup test' tab")
    except Exception as error:  # noqa: BLE001
        report(False, f"Google Sheet webhook failed: {error}",
               "Check SHEETS_WEBHOOK_URL ends in /exec, SHEETS_TOKEN matches TOKEN in the script, "
               "and the deployment has 'Who has access: Anyone'.")
else:
    print("[ -- ] Google Sheet not set up yet (optional): the demo offers a CSV download instead")

print()
print("All good. Next: streamlit run app.py   or   uvicorn api.main:app --reload" if problems == 0
      else f"{problems} problem(s) to fix above.")
sys.exit(1 if problems else 0)
