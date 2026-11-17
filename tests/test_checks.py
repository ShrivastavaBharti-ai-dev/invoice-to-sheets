"""GSTIN validation and the invoice checks."""
import json
from datetime import date
from pathlib import Path

import pytest

from invoiceflow import Invoice, gstin as G
from invoiceflow.validate import validate

ROOT = Path(__file__).resolve().parent.parent
KEY = json.loads((ROOT / "samples" / "answer_key.json").read_text(encoding="utf-8"))
TODAY = date(2026, 11, 14)


def sample(name="01_narmada_dairy.pdf", **changes):
    data = json.loads(json.dumps(KEY[name]["invoice"]))
    data.update(changes)
    return Invoice.model_validate(data)


def problems(inv, **kw):
    checks, status = validate(inv, today=TODAY, **kw)
    return {c.name: c.message for c in checks if c.status != "ok"}, status


def test_known_gstin_example_and_typo():
    assert G.problem("27AAPFU0939F1ZV") is None
    assert "check digit" in G.problem("27AAPFU0939F1ZX")
    assert "15" in G.problem("27AAPFU0939F1Z")
    assert "format" in G.problem("27AAPFU0939F1Z!")
    assert G.problem("") == "missing" and G.problem("00AAPFU0939F1Z0") == "has an unknown state code 00"


def test_gstin_helpers():
    built = G.make("23", "ABCDE1234F")
    assert G.problem(built) is None and G.state_of(built) == "23" and G.clean(" 23abc de ") == "23ABCDE"


@pytest.mark.parametrize("name", list(KEY))
def test_answer_key_status(name):
    _, status = problems(Invoice.model_validate(KEY[name]["invoice"]))
    assert status == KEY[name]["expected_status"]


def test_wrong_line_amount_blocks():
    found, status = problems(Invoice.model_validate(KEY["05_cleanpro_with_error.pdf"]["invoice"]))
    assert status == "blocked" and "1,850.00" in found["Line amounts"]


def test_subtotal_and_total_mismatch():
    found, status = problems(sample(subtotal=8000.0, total=9999.0))
    assert status == "blocked" and "Subtotal" in found and "Total" in found


def test_same_state_invoice_must_not_use_igst():
    found, _ = problems(sample(cgst=0, sgst=0, igst=586.0))
    assert "GST split" in found


def test_inter_state_invoice_must_use_igst():
    found, _ = problems(sample("04_spice_route_interstate.pdf", cgst=296.25, sgst=296.25, igst=0))
    assert "IGST only" in found["GST split"]


def test_dates():
    assert "future" in problems(sample(invoice_date="2027-01-01"))[0]["Invoice date"]
    assert "Can't read" in problems(sample(invoice_date="3rd Nov"))[0]["Invoice date"]
    found, status = problems(sample(invoice_date="2023-01-01"))
    assert "two years" in found["Invoice date"] and status == "check"


def test_missing_fields_and_no_lines():
    found, status = problems(sample(invoice_number="", line_items=[]))
    assert "invoice number" in found["Required fields"] and "Line items" in found and status == "blocked"


def test_missing_supplier_gstin_is_a_warning_bad_one_an_error():
    assert problems(sample(supplier_gstin=""))[1] == "check"
    assert problems(sample(supplier_gstin="23AAKFN5521Q1ZX"))[1] == "blocked"


def test_unreadable_fields_and_duplicates():
    found, status = problems(sample(unreadable_fields=["invoice_date"]))
    assert status == "check" and "invoice_date" in found["Unclear in the document"]
    found, status = problems(sample(), already_exported=True)
    assert status == "blocked" and "already" in found["Duplicate"]


def test_mixed_gst_rates_are_accepted():
    _, status = problems(Invoice.model_validate(KEY["06_indore_bakery_photo.jpg"]["invoice"]))
    assert status == "ready"


def test_model_cleans_values():
    inv = Invoice.model_validate({"supplier_gstin": " 23aakfn5521q1zw ", "invoice_number": None, "cgst": None})
    assert inv.supplier_gstin == "23AAKFN5521Q1ZW" and inv.invoice_number == "" and inv.cgst == 0
