"""Data shapes, validated with Pydantic."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    description: str = ""
    hsn: str = ""
    quantity: float = 0
    unit: str = ""
    rate: float = 0
    amount: float = 0


class Invoice(BaseModel):
    supplier_name: str = ""
    supplier_gstin: str = ""
    buyer_name: str = ""
    buyer_gstin: str = ""
    invoice_number: str = ""
    invoice_date: str = ""          # YYYY-MM-DD
    place_of_supply: str = ""
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float = 0
    cgst: float = 0
    sgst: float = 0
    igst: float = 0
    round_off: float = 0
    total: float = 0
    unreadable_fields: list[str] = Field(default_factory=list)

    @field_validator("supplier_gstin", "buyer_gstin", "invoice_number", mode="before")
    @classmethod
    def _strip(cls, value):
        return "" if value is None else str(value).strip().upper()

    @field_validator("supplier_name", "buyer_name", "invoice_date", "place_of_supply", mode="before")
    @classmethod
    def _text(cls, value):
        return "" if value is None else str(value).strip()

    @field_validator("subtotal", "cgst", "sgst", "igst", "round_off", "total", mode="before")
    @classmethod
    def _number(cls, value):
        return 0 if value in (None, "") else value


class Check(BaseModel):
    name: str
    status: Literal["ok", "warning", "error"]
    message: str


class ParseResult(BaseModel):
    invoice: Invoice
    checks: list[Check]
    status: Literal["ready", "check", "blocked"]
    source: str = ""
    reader: str = ""

    @property
    def problems(self) -> list[Check]:
        return [c for c in self.checks if c.status != "ok"]
