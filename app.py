"""InvoiceFlow demo screen.

    streamlit run app.py
"""
from __future__ import annotations

import datetime
import math
import os
from pathlib import Path

import pandas as pd

import streamlit as st

from invoiceflow import (
    ExportError,
    ExportRegistry,
    Invoice,
    LineItem,
    SheetWebhook,
    UnsupportedFile,
    check,
    export,
    make_reader,
    parse,
    to_csv,
)
from invoiceflow.readers import MIME_TYPES

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
MAX_READS_PER_SESSION = 10
# A global safety cap shared by every visitor (on top of the per-session limit),
# so a public demo can't run the owner's API key past a daily budget. Override
# with the MAX_LLM_CALLS_PER_DAY environment variable.
MAX_LLM_CALLS_PER_DAY = int(os.getenv("MAX_LLM_CALLS_PER_DAY", "200"))
CONTRA_URL = "https://contra.com/bharti_shrivastava_zu3hypce"
BADGE = {"ready": "✅ Ready to send", "check": "⚠️ Check the warnings", "blocked": "⛔ Blocked: fix the errors"}
ICON = {"ok": "✅", "warning": "⚠️", "error": "⛔"}


def setting(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    if any(p.exists() for p in [ROOT / ".streamlit" / "secrets.toml", Path.home() / ".streamlit" / "secrets.toml"]):
        try:
            return st.secrets.get(name)
        except Exception:  # noqa: BLE001
            return None
    return None


@st.cache_resource(show_spinner=False)
def get_reader(api_key: str | None):
    return make_reader(api_key)


@st.cache_resource(show_spinner=False)
def _daily_usage() -> dict:
    """One counter shared by all sessions in this server process."""
    return {"date": datetime.date.today(), "calls": 0}


def _roll_day(usage: dict) -> None:
    today = datetime.date.today()
    if usage["date"] != today:
        usage["date"], usage["calls"] = today, 0


def day_calls_left() -> int:
    usage = _daily_usage()
    _roll_day(usage)
    return MAX_LLM_CALLS_PER_DAY - usage["calls"]


def record_call() -> None:
    usage = _daily_usage()
    _roll_day(usage)
    usage["calls"] += 1


def is_rate_limit(error: Exception) -> bool:
    text = f"{type(error).__name__} {error}".lower()
    return any(s in text for s in ("429", "resource_exhausted", "quota", "rate limit"))


def main() -> None:
    st.set_page_config(page_title="InvoiceFlow: invoices to Google Sheets", page_icon="🧾", layout="wide")
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    api_key = setting("GOOGLE_API_KEY") or setting("GEMINI_API_KEY")
    if setting("GEMINI_CHAT_MODEL"):
        os.environ["GEMINI_CHAT_MODEL"] = setting("GEMINI_CHAT_MODEL")
    try:
        reader = get_reader(api_key)
    except Exception as error:  # noqa: BLE001
        st.error(f"Couldn't start Gemini ({type(error).__name__}). Using the no-key reader.")
        reader = get_reader(None)
    url, token = setting("SHEETS_WEBHOOK_URL"), setting("SHEETS_TOKEN")
    sheet = SheetWebhook(url, token) if url and token else None

    state = st.session_state
    state.setdefault("results", [])
    state.setdefault("current", None)
    state.setdefault("reads", 0)
    state.setdefault("registry", ExportRegistry())
    state.setdefault("sent", set())

    st.title("InvoiceFlow")
    st.markdown("**Upload a supplier invoice, PDF or phone photo. It's read, every GST calculation is checked, "
                "and it goes into Google Sheets.** Mistakes are caught before they reach your accounts.")
    st.caption("Sample invoices are fictional: suppliers of a made-up café in Bhopal. One contains a deliberate error.")
    st.caption("⏳ On the free demo server, the very first read can take up to a minute while it wakes up — "
               "after that it's quick.")

    # ---------------------------------------------------------------- sidebar
    with st.sidebar:
        if reader.live:
            st.success(f"Live: {reader.name.replace('gemini:', 'Gemini ')}")
            st.caption(f"Invoices left this session: {max(0, MAX_READS_PER_SESSION - state.reads)}")
        else:
            st.info("No-key mode: only the sample PDFs can be read. Add a GOOGLE_API_KEY to read photos and any layout.")
        st.header("Invoice")
        samples = sorted(p.name for p in SAMPLES.iterdir() if p.suffix.lower() in MIME_TYPES)
        choice = st.selectbox("Pick a sample", samples + ["Upload my own"],
                              format_func=lambda n: n.split("_", 1)[-1].rsplit(".", 1)[0].replace("_", " ").capitalize()
                              if n != "Upload my own" else n)
        data, name = None, None
        if choice == "Upload my own":
            upload = st.file_uploader("PDF, PNG, JPG or WEBP, up to 10 MB", type=["pdf", "png", "jpg", "jpeg", "webp"])
            if upload is not None:
                data, name = upload.getvalue(), upload.name
        else:
            data, name = (SAMPLES / choice).read_bytes(), choice
            st.download_button("Download this sample", data, file_name=choice)
        limit_hit = reader.live and state.reads >= MAX_READS_PER_SESSION
        day_hit = reader.live and day_calls_left() <= 0
        if st.button("Read invoice", type="primary", disabled=data is None or limit_hit or day_hit):
            try:
                with st.spinner("Reading and checking the invoice…"):
                    result = parse(data, name, reader, state.registry)
                if reader.live:
                    record_call()
                    state.reads += 1
                state.results.append(result)
                state.current = len(state.results) - 1
            except UnsupportedFile as error:
                st.warning(str(error))
            except Exception as error:  # noqa: BLE001
                st.error("The AI service is busy. Try again in a minute." if is_rate_limit(error)
                         else f"Couldn't read this file ({type(error).__name__}).")
        if limit_hit:
            st.caption("This demo reads 10 invoices per visit to stay inside its free API limit.")
        elif day_hit:
            st.caption("This public demo has paused for today after reaching its daily limit. "
                       "Please try again tomorrow, or run it yourself with your own key.")
        st.divider()
        st.caption(f"Built by Bharti Shrivastava · [Hire me on Contra]({CONTRA_URL})")

    if state.current is None:
        st.info("Pick a sample invoice on the left and press **Read invoice**. Try *Cleanpro with error* to see a "
                "mistake being caught, or the *photo* to see a phone picture being read (needs a Gemini key).")
        return

    index = state.current
    result = state.results[index]
    inv = result.invoice

    # ---------------------------------------------------------------- summary
    st.subheader(f"{BADGE[result.status]}: {inv.supplier_name or 'Unknown supplier'}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Invoice no", inv.invoice_number or "–")
    c2.metric("Date", inv.invoice_date or "–")
    c3.metric("GST", f"₹{inv.cgst + inv.sgst + inv.igst:,.2f}")
    c4.metric("Total", f"₹{inv.total:,.2f}")

    left, right = st.columns([3, 2])
    with right:
        st.markdown("**Checks**")
        for c in result.checks:
            st.markdown(f"{ICON[c.status]} **{c.name}**: {c.message}")
    with left:
        st.markdown("**Line items** (you can correct any value, then press Re-check)")
        table = pd.DataFrame([item.model_dump() for item in inv.line_items],
                             columns=["description", "hsn", "quantity", "unit", "rate", "amount"])
        edited = st.data_editor(table, num_rows="dynamic", key=f"items-{index}")
        with st.expander("Invoice details"):
            a, b = st.columns(2)
            supplier = a.text_input("Supplier", inv.supplier_name, key=f"sup-{index}")
            gstin = b.text_input("Supplier GSTIN", inv.supplier_gstin, key=f"gst-{index}")
            number = a.text_input("Invoice no", inv.invoice_number, key=f"num-{index}")
            when = b.text_input("Invoice date (YYYY-MM-DD)", inv.invoice_date, key=f"date-{index}")
            amounts = {}
            cols = st.columns(6)
            for col, field in zip(cols, ["subtotal", "cgst", "sgst", "igst", "round_off", "total"]):
                amounts[field] = col.number_input(field.replace("_", " ").upper() if len(field) < 5 else
                                                  field.replace("_", " ").capitalize(),
                                                  value=float(getattr(inv, field)), step=0.5, format="%.2f",
                                                  key=f"{field}-{index}")
        if st.button("Re-check"):
            items = []
            for record in edited.to_dict("records"):
                values = {k: v for k, v in record.items()
                          if v is not None and not (isinstance(v, float) and math.isnan(v))}
                if any(v not in ("", 0) for v in values.values()):
                    values["hsn"] = str(values.get("hsn", ""))
                    items.append(LineItem.model_validate(values))
            fixed = inv.model_copy(update={"supplier_name": supplier, "supplier_gstin": gstin.strip().upper(),
                                           "invoice_number": number.strip().upper(), "invoice_date": when.strip(),
                                           "line_items": items, "unreadable_fields": [], **amounts})
            state.results[index] = check(Invoice.model_validate(fixed.model_dump()), result.source, "edited",
                                         state.registry)
            st.rerun()

    # ---------------------------------------------------------------- send
    st.divider()
    a, b = st.columns(2)
    with a:
        if sheet is None:
            st.caption("Google Sheet not connected in this demo. Use the CSV download, or see the README to connect one.")
        else:
            force = False
            if result.status == "blocked":
                force = st.checkbox("I've checked this invoice; send it anyway", key=f"force-{index}")
            if st.button("Send to Google Sheet", type="primary", disabled=index in state.sent):
                try:
                    rows = export(result, sheet, state.registry, force=force)
                    state.sent.add(index)
                    st.success(f"Added to the sheet ({rows} rows).")
                except ExportError as error:
                    st.error(str(error))
    with b:
        st.download_button(f"Download CSV ({len(state.results)} invoice(s) read this session)",
                           to_csv(state.results), file_name="invoices.csv", mime="text/csv")

    if len(state.results) > 1:
        with st.expander("Invoices read this session"):
            for n, r in enumerate(state.results):
                if st.button(f"{BADGE[r.status].split(':')[0]} {r.invoice.supplier_name}: {r.invoice.invoice_number}",
                             key=f"pick-{n}"):
                    state.current = n
                    st.rerun()


main()
