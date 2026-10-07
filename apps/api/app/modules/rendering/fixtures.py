"""Sample documents: template previews (settings → branding) and the template test fixture sets.

Variants (plan §3.2 "Templates"): ``standard``, ``long_names``, ``many_lines`` (150), ``zero_dp`` (UGX),
``rtl`` (right-to-left text).
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from app.modules.rendering.view import (
    AmountLine,
    DocType,
    DocumentView,
    KeyValue,
    LineItem,
    Party,
    PaymentInstructions,
    Totals,
)

Variant = Literal["standard", "long_names", "many_lines", "zero_dp", "rtl"]
VARIANTS: tuple[Variant, ...] = ("standard", "long_names", "many_lines", "zero_dp", "rtl")

_ISSUED = date(2026, 10, 7)


def _lines(variant: Variant) -> list[LineItem]:
    if variant == "many_lines":
        return [
            LineItem(
                description=f"Item {n}: group life cover, member {n}",
                quantity=Decimal(1),
                unit_price=Decimal("1250.00"),
                amount=Decimal("1250.00"),
            )
            for n in range(1, 151)
        ]
    if variant == "zero_dp":
        return [
            LineItem(
                description="Motor private comprehensive",
                quantity=Decimal(1),
                unit_price=Decimal(1850000),
                amount=Decimal(1850000),
            )
        ]
    description = (
        "Motor private comprehensive: Toyota Land Cruiser Prado TX-L 2.8 GD-6, fleet of the "
        "Nairobi Western Regional Office, including windscreen, radio and political violence extensions"
        if variant == "long_names"
        else "Motor private comprehensive, KDA 123A"
    )
    if variant == "rtl":
        description = "تأمين شامل للسيارة / Comprehensive motor cover"
    return [
        LineItem(
            description=description,
            details="Period 07 Oct 2026 to 06 Oct 2027\nSum insured KES 3,500,000",
            quantity=Decimal(1),
            unit_price=Decimal("140000.00"),
            amount=Decimal("140000.00"),
        ),
        LineItem(
            description="Excess protector",
            quantity=Decimal(1),
            unit_price=Decimal("5000.00"),
            amount=Decimal("5000.00"),
        ),
    ]


def sample_view(
    doc_type: DocType = "quote", variant: Variant = "standard", *, seller_name: str | None = None
) -> DocumentView:
    lines = _lines(variant)
    currency = "UGX" if variant == "zero_dp" else "KES"
    subtotal = sum((line.amount for line in lines), Decimal(0))
    # Illustrative only: real levies come from the jurisdiction pack through app/calc.
    charges = [
        AmountLine(
            label="Training levy (0.2%)",
            amount=(subtotal * Decimal("0.002")).quantize(Decimal("0.01")),
        ),
        AmountLine(
            label="PHCF (0.25%)", amount=(subtotal * Decimal("0.0025")).quantize(Decimal("0.01"))
        ),
        AmountLine(label="Stamp duty", amount=Decimal(40)),
    ]
    total = subtotal + sum((c.amount for c in charges), Decimal(0))
    long = variant == "long_names"
    return DocumentView(
        doc_type=doc_type,
        number={
            "quote": "QT-2026-00042",
            "invoice": "INV-2026-00042",
            "receipt": "RCT-2026-00042",
            "credit_note": "CN-2026-00042",
        }[doc_type],
        issue_date=_ISSUED,
        due_date=_ISSUED + timedelta(days=14) if doc_type == "invoice" else None,
        valid_until=_ISSUED + timedelta(days=30) if doc_type == "quote" else None,
        currency=currency,
        seller=Party(
            name=seller_name
            or (
                "Wanjiku & Associates Insurance Agency Limited (Westlands Branch)"
                if long
                else "Wanjiku Insurance Agency"
            ),
            address_lines=["Westlands Business Park, 3rd Floor", "P.O. Box 12345-00100, Nairobi"],
            tax_pin="P051234567X",
            email="hello@wanjiku.co.ke",
            phone="+254 712 345 678",
        ),
        buyer=Party(
            name="Bwana Otieno Ochieng' Odhiambo Kamau-Wekesa of Kisumu Lakeside Estates"
            if long
            else "Otieno Ochieng",
            address_lines=["Milimani Road", "Kisumu"],
            email="otieno@example.com",
        ),
        details=[
            KeyValue(label="Insurer", value="Example General Insurance Ltd"),
            KeyValue(label="Cover", value="Comprehensive, private use"),
            KeyValue(label="Vehicle", value="KDA 123A, Toyota Prado 2022"),
        ],
        lines=lines,
        totals=Totals(
            subtotal=subtotal,
            charges=charges,
            total=total,
            amount_paid=total if doc_type == "receipt" else None,
            balance=Decimal(0)
            if doc_type == "receipt"
            else (total if doc_type == "invoice" else None),
        ),
        notes="Premium is payable to the insurer before cover starts."
        if doc_type != "receipt"
        else None,
        terms="This quotation is valid for 30 days and subject to the insurer's terms."
        if doc_type == "quote"
        else None,
        payment=PaymentInstructions(
            reference="T7Y2K7FXQH",
            mpesa_paybill="123456",
            bank_name="Example Bank",
            bank_account_name="Wanjiku Insurance Agency",
            bank_account_number="0123456789",
        )
        if doc_type == "invoice"
        else None,
        stamp="PAID" if doc_type == "receipt" else None,
    )
