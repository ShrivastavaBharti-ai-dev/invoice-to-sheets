"""Compare readers on the sample invoices against the answer key.

    python eval/run_eval.py             # no-key text reader vs Gemini (if a key is set)
    python eval/run_eval.py --offline   # text reader only

Writes eval/results.md; a Gemini run also updates the table in README.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from invoiceflow import Invoice, TextRulesReader, UnsupportedFile, make_reader, parse  # noqa: E402

HEADER_FIELDS = ["supplier_gstin", "buyer_gstin", "invoice_number", "invoice_date", "subtotal", "cgst", "sgst",
                 "igst", "round_off", "total"]
README_START, README_END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 0.01
    return str(a).strip().upper() == str(b).strip().upper()


def score(reader, key: dict, pause: float) -> dict:
    read = header = header_total = items_exact = status_ok = caught = errors_total = 0
    rows = []
    for name, truth in key.items():
        expected = Invoice.model_validate(truth["invoice"])
        header_total += len(HEADER_FIELDS)
        errors_total += truth["expected_status"] == "blocked"
        try:
            result = parse((ROOT / "samples" / name).read_bytes(), name, reader, today=date(2026, 11, 14))
        except UnsupportedFile as error:
            rows.append(f"| {name} | not read: {error} | | |")
            continue
        finally:
            time.sleep(pause)
        read += 1
        got = result.invoice
        hits = sum(same(getattr(got, f), getattr(expected, f)) for f in HEADER_FIELDS)
        header += hits
        lines_ok = len(got.line_items) == len(expected.line_items) and all(
            same(a.quantity, b.quantity) and same(a.rate, b.rate) and same(a.amount, b.amount)
            for a, b in zip(got.line_items, expected.line_items))
        items_exact += lines_ok
        status_ok += result.status == truth["expected_status"]
        caught += truth["expected_status"] == "blocked" and result.status == "blocked"
        rows.append(f"| {name} | {hits}/{len(HEADER_FIELDS)} | {'yes' if lines_ok else 'no'} | "
                    f"{result.status} (expected {truth['expected_status']}) |")
    n = len(key)
    return {"read": f"{read}/{n}", "header": f"{header}/{header_total}", "items": f"{items_exact}/{n}",
            "status": f"{status_ok}/{n}", "caught": f"{caught}/{errors_total}", "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--pause", type=float, default=6.0, help="seconds between Gemini calls")
    parser.add_argument("--no-readme", action="store_true")
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    key = json.loads((ROOT / "samples" / "answer_key.json").read_text(encoding="utf-8"))
    readers = [("Text rules (no key)", TextRulesReader(), 0.0)]
    if not args.offline:
        reader = make_reader()
        if reader.live:
            readers.append((f"Gemini (`{reader.model}`)", reader, args.pause))
        else:
            print("No GOOGLE_API_KEY found: running the text reader only.\n")

    results = {name: score(reader, key, pause) for name, reader, pause in readers}
    names = list(results)
    lines = ["| | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names)]
    for field, label in [("read", "Invoices read (5 PDFs + 1 phone photo)"),
                         ("header", "Header fields exactly right (GSTINs, number, date, amounts)"),
                         ("items", "Invoices with every line item right"),
                         ("status", "Correct ready / blocked decision"),
                         ("caught", "Invoices with a printed arithmetic error caught")]:
        lines.append(f"| {label} | " + " | ".join(results[n][field] for n in names) + " |")
    report = (f"Measured on {date.today():%d %b %Y} on 6 fictional supplier invoices in three layouts, one of them a "
              "tilted phone photo and one with a deliberate arithmetic error.\n\n" + "\n".join(lines) +
              "\n\nThe text reader was written for these sample layouts, so it only shows what a no-AI approach "
              "can do on known, clean PDFs. It can't read photos or new layouts.")
    detail = ["", "## Each invoice", ""]
    for name in names:
        detail += [f"### {name}", "", "| File | Header fields | Line items | Decision |", "|---|---|---|---|"]
        detail += results[name]["rows"] + [""]
    (ROOT / "eval" / "results.md").write_text("# Evaluation results\n\n" + report + "\n" + "\n".join(detail),
                                               encoding="utf-8")
    print(report + "\n\nSaved eval/results.md")

    readme = ROOT / "README.md"
    if len(names) > 1 and not args.no_readme and readme.exists():
        text = readme.read_text(encoding="utf-8")
        if README_START in text and README_END in text:
            head, rest = text.split(README_START, 1)
            _, tail = rest.split(README_END, 1)
            readme.write_text(f"{head}{README_START}\n{report}\n{README_END}{tail}", encoding="utf-8")
            print("Updated the results table in README.md")


if __name__ == "__main__":
    main()
