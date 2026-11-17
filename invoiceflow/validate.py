"""Checks every extracted invoice before it reaches the spreadsheet.

The AI only reads the document. Whether the numbers add up, the GST is split
correctly and the GSTIN is real is decided here, in plain code.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import gstin as G
from .models import Check, Invoice

TOLERANCE = 1.0                  # rupees: printed amounts are rounded
GST_RATES = (0, 5, 12, 18, 28)   # %


def _money(x: float) -> str:
    return f"₹{x:,.2f}"


def _status(checks: list[Check]) -> str:
    if any(c.status == "error" for c in checks):
        return "blocked"
    if any(c.status == "warning" for c in checks):
        return "check"
    return "ready"


def validate(inv: Invoice, today: date | None = None, already_exported: bool = False) -> tuple[list[Check], str]:
    today = today or date.today()
    checks: list[Check] = []

    def add(name: str, ok: bool, message: str, severity: str = "error", ok_message: str = "") -> None:
        checks.append(Check(name=name, status="ok" if ok else severity, message=ok_message if ok else message))

    # Required fields
    missing = [label for label, value in [("supplier name", inv.supplier_name), ("invoice number", inv.invoice_number),
                                          ("invoice date", inv.invoice_date), ("total", inv.total)] if not value]
    add("Required fields", not missing, "Missing: " + ", ".join(missing), ok_message="All present")

    # Date
    try:
        when = date.fromisoformat(inv.invoice_date)
        if when > today:
            add("Invoice date", False, f"{when:%d %b %Y} is in the future")
        elif when < today - timedelta(days=365 * 2):
            add("Invoice date", False, f"{when:%d %b %Y} is more than two years old", "warning")
        else:
            add("Invoice date", True, "", ok_message=f"{when:%d %b %Y}")
    except ValueError:
        add("Invoice date", False, f"Can't read the date '{inv.invoice_date}'")

    # GSTINs
    supplier_issue = G.problem(inv.supplier_gstin)
    add("Supplier GSTIN", supplier_issue is None, f"Supplier GSTIN {supplier_issue}",
        "warning" if supplier_issue == "missing" else "error", ok_message=G.clean(inv.supplier_gstin))
    if inv.buyer_gstin:
        buyer_issue = G.problem(inv.buyer_gstin)
        add("Buyer GSTIN", buyer_issue is None, f"Buyer GSTIN {buyer_issue}", ok_message=G.clean(inv.buyer_gstin))

    # Line items
    if not inv.line_items:
        add("Line items", False, "No line items found")
    else:
        wrong = [f"line {n}: {item.quantity:g} x {_money(item.rate)} = {_money(item.quantity * item.rate)}, "
                 f"printed {_money(item.amount)}"
                 for n, item in enumerate(inv.line_items, 1)
                 if abs(item.quantity * item.rate - item.amount) > TOLERANCE]
        add("Line amounts", not wrong, "; ".join(wrong), ok_message=f"{len(inv.line_items)} lines add up")
        lines_total = sum(item.amount for item in inv.line_items)
        add("Subtotal", abs(lines_total - inv.subtotal) <= TOLERANCE,
            f"Lines add up to {_money(lines_total)} but the subtotal says {_money(inv.subtotal)}",
            ok_message=_money(inv.subtotal))

    # Tax split: same state -> CGST + SGST, different states -> IGST
    supplier_state, buyer_state = G.state_of(inv.supplier_gstin), G.state_of(inv.buyer_gstin)
    tax = inv.cgst + inv.sgst + inv.igst
    if supplier_state and buyer_state:
        if supplier_state == buyer_state:
            ok = inv.igst == 0 and abs(inv.cgst - inv.sgst) <= TOLERANCE
            add("GST split", ok, "Same-state invoice should have equal CGST and SGST and no IGST",
                ok_message="CGST + SGST (same state)")
        else:
            ok = inv.cgst == 0 and inv.sgst == 0
            add("GST split", ok, "Inter-state invoice should have IGST only, not CGST/SGST",
                ok_message=f"IGST (from {G.STATES[supplier_state]})")
    if inv.subtotal > 0 and tax > 0:
        rate = 100 * tax / inv.subtotal
        single = any(abs(rate - r) <= 0.5 for r in GST_RATES)
        mixed = 0 < rate < 28
        add("GST rate", single or mixed, f"GST is {rate:.1f}% of the subtotal, which is unusual",
            "warning", ok_message=f"{rate:.1f}%" + ("" if single else " (mixed rates)"))

    # Grand total
    expected = inv.subtotal + tax + inv.round_off
    add("Total", abs(expected - inv.total) <= TOLERANCE,
        f"Subtotal + GST + round-off = {_money(expected)}, but the total says {_money(inv.total)}",
        ok_message=_money(inv.total))
    if abs(inv.round_off) > 1:
        add("Round-off", False, f"Round-off of {_money(inv.round_off)} is larger than ₹1", "warning")

    # What the reader itself was unsure about
    if inv.unreadable_fields:
        add("Unclear in the document", False, "Please check: " + ", ".join(inv.unreadable_fields[:6]), "warning")

    if already_exported:
        add("Duplicate", False, f"Invoice {inv.invoice_number} from this supplier was already sent to the sheet")

    return checks, _status(checks)
