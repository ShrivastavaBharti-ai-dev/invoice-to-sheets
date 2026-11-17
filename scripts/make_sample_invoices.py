"""Generate the fictional sample invoices in samples/ and their answer key.

    python scripts/make_sample_invoices.py

Requires reportlab, pypdfium2 and Pillow (only needed to regenerate the samples).
All businesses, GSTINs and invoices are fictional; the GSTINs are built with a
valid check digit so they pass format checks.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from invoiceflow.gstin import make  # noqa: E402

OUT = ROOT / "samples"
FONT, BOLD, RUPEE = "Helvetica", "Helvetica-Bold", "Rs."
for regular, bold in [("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]:
    if Path(regular).exists():
        pdfmetrics.registerFont(TTFont("DejaVu", regular))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold))
        FONT, BOLD, RUPEE = "DejaVu", "DejaVu-Bold", "₹"

BUYER = {"name": "Chai & Crumb Café", "address": "14 Arera Colony, Bhopal, Madhya Pradesh",
         "gstin": make("23", "AAFCC4821M")}


def item(description, hsn, qty, unit, rate, amount=None):
    return {"description": description, "hsn": hsn, "quantity": qty, "unit": unit, "rate": rate,
            "amount": round(qty * rate, 2) if amount is None else amount}


INVOICES = [
    {"file": "01_narmada_dairy.pdf", "layout": "classic",
     "supplier": {"name": "Narmada Dairy Suppliers", "address": "Plot 7, Govindpura Industrial Area, Bhopal",
                  "gstin": make("23", "AAKFN5521Q")},
     "number": "DS/26-27/0412", "date": "2026-11-03",
     "items": [item("Paneer (fresh)", "0406", 10, "kg", 380), item("Butter (unsalted)", "0405", 5, "kg", 520),
               item("Fresh cream", "0401", 8, "litre", 210)],
     "cgst": 293.00, "sgst": 293.00, "igst": 0, "round_off": 0},
    {"file": "02_bhopal_fresh_produce.pdf", "layout": "modern",
     "supplier": {"name": "Bhopal Fresh Produce Co.", "address": "Shop 21, Karond Sabzi Mandi, Bhopal",
                  "gstin": make("23", "ABOFB7710R")},
     "number": "BFP-2026-1187", "date": "2026-11-05",
     "items": [item("Tomatoes", "0702", 25, "kg", 32), item("Onions", "0703", 30, "kg", 28),
               item("Potatoes", "0701", 20, "kg", 24), item("Coriander leaves", "0709", 3, "kg", 90),
               item("Green chillies", "0709", 2, "kg", 70)],
     "cgst": 0, "sgst": 0, "igst": 0, "round_off": 0},
    {"file": "03_malwa_packaging.pdf", "layout": "compact",
     "supplier": {"name": "Malwa Packaging Solutions", "address": "45 Mandideep Industrial Estate, Raisen",
                  "gstin": make("23", "AARFM3349L")},
     "number": "MPS/1543", "date": "2026-10-28",
     "items": [item("Paper cups 250 ml", "4823", 2000, "pcs", 1.20), item("Kraft takeaway boxes", "4819", 500, "pcs", 6.50),
               item("Butter paper roll", "4823", 10, "roll", 145), item("Wooden stirrers", "4421", 1000, "pcs", 0.35)],
     "cgst": 670.50, "sgst": 670.50, "igst": 0, "round_off": 0},
    {"file": "04_spice_route_interstate.pdf", "layout": "classic",
     "supplier": {"name": "Spice Route Traders", "address": "88 Itwari Market, Nagpur, Maharashtra",
                  "gstin": make("27", "ADEFS9012H")},
     "number": "SRT/2026/0778", "date": "2026-11-07",
     "items": [item("Cardamom (green)", "0908", 2, "kg", 2400), item("Cinnamon sticks", "0906", 3, "kg", 650),
               item("Assam CTC tea", "0902", 15, "kg", 340)],
     "cgst": 0, "sgst": 0, "igst": 592.50, "round_off": -0.50},
    {"file": "05_cleanpro_with_error.pdf", "layout": "modern",
     "supplier": {"name": "CleanPro Hygiene Supplies", "address": "B-12 Zone II, MP Nagar, Bhopal",
                  "gstin": make("23", "AAGFC6687D")},
     "number": "CP-INV-2291", "date": "2026-11-10",
     # Deliberate mistake: 4 x 450 is 1,800 but the supplier printed 1,850.
     "items": [item("Floor cleaner 5 L", "3402", 4, "can", 450, amount=1850.00), item("Dishwash liquid 5 L", "3402", 6, "can", 380),
               item("Garbage bags (large)", "3923", 10, "pack", 120), item("Hand sanitiser 500 ml", "3808", 8, "bottle", 165)],
     "cgst": 598.50, "sgst": 598.50, "igst": 0, "round_off": 0},
    {"file": "06_indore_bakery_photo.pdf", "layout": "compact", "photo": "06_indore_bakery_photo.jpg",
     "supplier": {"name": "Indore Bakery Ingredients", "address": "201 Siyaganj Main Road, Indore",
                  "gstin": make("23", "AAJFI2234B")},
     "number": "IBI/26/3310", "date": "2026-11-11",
     "items": [item("Maida (refined flour)", "1101", 50, "kg", 42), item("Cocoa powder", "1805", 5, "kg", 610),
               item("Baking powder", "2102", 2, "kg", 240), item("Dark chocolate compound", "1806", 10, "kg", 395)],
     "cgst": 725.70, "sgst": 725.70, "igst": 0, "round_off": -0.40},
]


def money(x: float) -> str:
    return f"{x:,.2f}"


def totals(inv: dict) -> dict:
    subtotal = round(sum(i["amount"] for i in inv["items"]), 2)
    total = round(subtotal + inv["cgst"] + inv["sgst"] + inv["igst"] + inv["round_off"], 2)
    return {"subtotal": subtotal, "total": total}


def draw(inv: dict, path: Path) -> None:
    t = totals(inv)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    left, right = 18 * mm, width - 18 * mm
    accent = {"classic": colors.HexColor("#1F3A5F"), "modern": colors.HexColor("#0F766E"),
              "compact": colors.HexColor("#7C2D12")}[inv["layout"]]
    sup = inv["supplier"]
    d = inv["date"]
    printed_date = f"{d[8:10]}/{d[5:7]}/{d[0:4]}"  # Indian DD/MM/YYYY

    y = height - 20 * mm
    if inv["layout"] == "modern":
        c.setFillColor(accent)
        c.rect(0, height - 42 * mm, width, 42 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(BOLD, 20)
        c.drawString(left, y - 4 * mm, sup["name"])
        c.setFont(FONT, 9.5)
        c.drawString(left, y - 11 * mm, sup["address"])
        c.drawString(left, y - 16 * mm, f"GSTIN: {sup['gstin']}")
        c.setFont(BOLD, 15)
        c.drawRightString(right, y - 4 * mm, "TAX INVOICE")
        c.setFillColor(colors.black)
        y = height - 52 * mm
    else:
        c.setFillColor(accent)
        c.setFont(BOLD, 18 if inv["layout"] == "classic" else 15)
        c.drawString(left, y, sup["name"])
        c.setFillColor(colors.black)
        c.setFont(FONT, 9.5)
        c.drawString(left, y - 6 * mm, sup["address"])
        c.drawString(left, y - 11 * mm, f"GSTIN: {sup['gstin']}")
        c.setFont(BOLD, 13)
        c.drawRightString(right, y, "TAX INVOICE")
        c.setStrokeColor(accent)
        c.setLineWidth(1.2)
        c.line(left, y - 15 * mm, right, y - 15 * mm)
        y -= 24 * mm

    c.setFont(FONT, 10)
    c.drawString(left, y, f"Invoice No: {inv['number']}")
    c.drawString(left, y - 5.5 * mm, f"Invoice Date: {printed_date}")
    c.drawString(left, y - 11 * mm, "Place of Supply: Madhya Pradesh (23)")
    c.setFont(BOLD, 10)
    c.drawString(width / 2 + 5 * mm, y, "Bill To:")
    c.setFont(FONT, 10)
    c.drawString(width / 2 + 5 * mm, y - 5.5 * mm, BUYER["name"])
    c.drawString(width / 2 + 5 * mm, y - 11 * mm, BUYER["address"])
    c.drawString(width / 2 + 5 * mm, y - 16.5 * mm, f"GSTIN: {BUYER['gstin']}")
    y -= 28 * mm

    cols = [left, left + 10 * mm, left + 78 * mm, left + 94 * mm, left + 108 * mm]
    rate_right = left + 140 * mm
    c.setFillColor(accent if inv["layout"] != "classic" else colors.HexColor("#E8EEF5"))
    c.rect(left, y - 2.5 * mm, right - left, 8 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white if inv["layout"] != "classic" else colors.black)
    c.setFont(BOLD, 9.5)
    for x, label in zip(cols, ["#", "Description", "HSN", "Qty", "Unit"]):
        c.drawString(x + 1.5 * mm, y, label)
    c.drawRightString(rate_right, y, f"Rate ({RUPEE})")
    c.drawRightString(right - 1.5 * mm, y, f"Amount ({RUPEE})")
    c.setFillColor(colors.black)
    c.setFont(FONT, 9.5)
    y -= 9 * mm
    for n, it in enumerate(inv["items"], 1):
        qty = f"{it['quantity']:g}"
        for x, value in zip(cols, [str(n), it["description"], it["hsn"], qty, it["unit"]]):
            c.drawString(x + 1.5 * mm, y, value)
        c.drawRightString(rate_right, y, money(it["rate"]))
        c.drawRightString(right - 1.5 * mm, y, money(it["amount"]))
        c.setStrokeColor(colors.HexColor("#DDDDDD"))
        c.setLineWidth(0.5)
        c.line(left, y - 3 * mm, right, y - 3 * mm)
        y -= 8 * mm

    y -= 4 * mm
    rows = [("Subtotal", t["subtotal"])]
    if inv["cgst"] or inv["sgst"]:
        rows += [("CGST", inv["cgst"]), ("SGST", inv["sgst"])]
    if inv["igst"]:
        rows += [("IGST", inv["igst"])]
    if not (inv["cgst"] or inv["sgst"] or inv["igst"]):
        rows += [("GST (exempt goods)", 0.0)]
    if inv["round_off"]:
        rows += [("Round Off", inv["round_off"])]
    for label, value in rows:
        c.setFont(FONT, 10)
        c.drawRightString(rate_right, y, label)
        c.drawRightString(right - 1.5 * mm, y, money(value))
        y -= 6 * mm
    c.setFont(BOLD, 12)
    c.setFillColor(accent)
    c.drawRightString(left + 132 * mm, y - 2 * mm, "Grand Total")
    c.drawRightString(right - 1.5 * mm, y - 2 * mm, f"{RUPEE} {money(t['total'])}")
    c.setFillColor(colors.black)

    c.setFont(FONT, 8.5)
    c.drawString(left, 22 * mm, "Payment terms: within 15 days by bank transfer or UPI. Goods once sold will not be taken back.")
    c.setFillColor(colors.HexColor("#888888"))
    c.drawString(left, 15 * mm, "Fictional invoice generated for a software demo. Not a real business or tax document.")
    c.showPage()
    c.save()


def make_photo(pdf: Path, out: Path) -> None:
    """Turn the PDF into a slightly tilted, uneven 'phone photo'."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageEnhance, ImageFilter

    page = pdfium.PdfDocument(str(pdf))[0]
    image = page.render(scale=1.6).to_pil().convert("RGB")
    rng = random.Random(7)
    background = Image.new("RGB", (image.width + 160, image.height + 160), (92, 78, 64))
    paper = ImageEnhance.Color(image).enhance(0.9)
    paper = Image.blend(paper, Image.new("RGB", paper.size, (246, 238, 220)), 0.12)
    background.paste(paper, (80, 80))
    photo = background.rotate(1.8, resample=Image.BICUBIC, fillcolor=(92, 78, 64))
    shade = Image.linear_gradient("L").resize(photo.size).point(lambda v: int(v * 0.35))
    photo = Image.composite(Image.new("RGB", photo.size, (40, 32, 24)), photo, shade)
    noise = Image.effect_noise(photo.size, 18).convert("RGB")
    photo = Image.blend(photo, noise, 0.06).filter(ImageFilter.GaussianBlur(0.6))
    photo = photo.resize((int(photo.width * 0.85), int(photo.height * 0.85)))
    photo.save(out, "JPEG", quality=82)
    _ = rng


def main() -> None:
    OUT.mkdir(exist_ok=True)
    truth = {}
    for inv in INVOICES:
        pdf = OUT / inv["file"]
        draw(inv, pdf)
        record = {
            "supplier_name": inv["supplier"]["name"], "supplier_gstin": inv["supplier"]["gstin"],
            "buyer_name": BUYER["name"], "buyer_gstin": BUYER["gstin"], "invoice_number": inv["number"],
            "invoice_date": inv["date"], "place_of_supply": "Madhya Pradesh",
            "line_items": inv["items"], **totals(inv),
            "cgst": inv["cgst"], "sgst": inv["sgst"], "igst": inv["igst"], "round_off": inv["round_off"],
        }
        expected_status = "blocked" if "error" in inv["file"] else "ready"
        files = [inv["file"]]
        if inv.get("photo"):
            make_photo(pdf, OUT / inv["photo"])
            pdf.unlink()
            files = [inv["photo"]]
        for name in files:
            truth[name] = {"invoice": record, "expected_status": expected_status}
        print("wrote", files[0])
    (OUT / "answer_key.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote answer_key.json")


if __name__ == "__main__":
    main()
