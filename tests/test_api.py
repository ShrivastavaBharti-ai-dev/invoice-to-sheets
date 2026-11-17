"""HTTP API. Needs fastapi, httpx and python-multipart (pip install -r requirements-dev.txt)."""
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client():
    # Empty values (not deleted) so load_dotenv() can't fill them from your .env: tests stay offline and free.
    saved = {k: os.environ.get(k) for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "SHEETS_WEBHOOK_URL", "APP_API_KEY")}
    for k in saved:
        os.environ[k] = ""
    from fastapi.testclient import TestClient
    from api.main import app
    yield TestClient(app)
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def upload(client, name, content=None):
    data = content if content is not None else (ROOT / "samples" / name).read_bytes()
    return client.post("/invoices/parse", files={"file": (name, data, "application/octet-stream")})


def test_health(client):
    assert client.get("/health").json()["reader"] == "text-rules"


def test_parse_sample_pdf(client):
    body = upload(client, "05_cleanpro_with_error.pdf").json()
    assert body["status"] == "blocked" and body["invoice"]["invoice_number"] == "CP-INV-2291"
    assert any(c["name"] == "Line amounts" and c["status"] == "error" for c in body["checks"])


def test_unsupported_file(client):
    assert upload(client, "notes.txt", b"hello").status_code == 415


def test_check_corrected_invoice(client):
    body = upload(client, "05_cleanpro_with_error.pdf").json()
    invoice = body["invoice"]
    invoice["line_items"][0]["amount"] = 1800.0
    invoice["subtotal"], invoice["cgst"], invoice["sgst"], invoice["total"] = 6600.0, 594.0, 594.0, 7788.0
    fixed = client.post("/invoices/check", json={"invoice": invoice}).json()
    assert fixed["status"] == "ready"


def test_export_without_sheet_is_503(client):
    import uuid
    invoice = upload(client, "01_narmada_dairy.pdf").json()["invoice"]
    invoice["invoice_number"] = f"TEST-{uuid.uuid4().hex[:8]}"  # never seen before, even if you exported the sample
    assert client.post("/invoices/export", json={"invoice": invoice}).status_code == 503
