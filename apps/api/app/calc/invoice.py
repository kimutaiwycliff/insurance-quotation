"""Invoice arithmetic (pure): line amounts, VAT inclusive or exclusive, discounts, totals, payment allocation.

Rounding happens per line to the currency's minor unit with the pack's rounding mode (KRA computes VAT per
line on eTIMS), so a document's tax always equals the sum of its lines' tax. Tax rates come from the
jurisdiction pack's tax codes, never from code.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.calc.pack import Pack
from app.core.money import Money

ZERO = Decimal(0)


class InvoiceInputError(ValueError):
    pass


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    discount_rate: Decimal = Field(default=ZERO, ge=0, le=1)
    tax_code: str


class LineOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    gross: Decimal = Field(description="quantity x unit price, before discount")
    discount: Decimal
    net: Decimal = Field(description="excluding tax")
    tax_code: str
    tax_rate: Decimal
    tax: Decimal
    total: Decimal = Field(description="including tax")


class TaxSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    rate: Decimal
    taxable: Decimal
    tax: Decimal


class InvoiceTotals(BaseModel):
    model_config = ConfigDict(frozen=True)

    lines: list[LineOut]
    subtotal: Decimal = Field(description="sum of line nets (excluding tax)")
    discount: Decimal
    tax: Decimal
    total: Decimal
    taxes: list[TaxSummary]


def _round(pack: Pack, amount: Decimal, currency: str) -> Decimal:
    return Money(amount, currency).rounded(pack.rounding).amount


def calculate_invoice(
    pack: Pack, lines: list[LineIn], *, currency: str, prices_include_tax: bool
) -> InvoiceTotals:
    if not lines:
        raise InvoiceInputError("An invoice needs at least one line")
    codes = {t.code: t for t in pack.tax_codes}
    out: list[LineOut] = []
    for line in lines:
        tax = codes.get(line.tax_code)
        if tax is None:
            raise InvoiceInputError(f"Unknown tax code {line.tax_code!r}")
        gross = _round(pack, line.quantity * line.unit_price, currency)
        discount = _round(pack, gross * line.discount_rate, currency)
        after = gross - discount
        if prices_include_tax:
            total = after
            net = _round(pack, total / (1 + tax.rate), currency)
            tax_amount = total - net
        else:
            net = after
            tax_amount = _round(pack, net * tax.rate, currency)
            total = net + tax_amount
        out.append(
            LineOut(
                gross=gross,
                discount=discount,
                net=net,
                tax_code=tax.code,
                tax_rate=tax.rate,
                tax=tax_amount,
                total=total,
            )
        )
    summary: dict[str, list[Decimal]] = {}
    for row in out:
        summary.setdefault(row.tax_code, [ZERO, ZERO])
        summary[row.tax_code][0] += row.net
        summary[row.tax_code][1] += row.tax
    return InvoiceTotals(
        lines=out,
        subtotal=sum((row.net for row in out), ZERO),
        discount=sum((row.discount for row in out), ZERO),
        tax=sum((row.tax for row in out), ZERO),
        total=sum((row.total for row in out), ZERO),
        taxes=[
            TaxSummary(
                code=code, name=codes[code].name, rate=codes[code].rate, taxable=t[0], tax=t[1]
            )
            for code, t in summary.items()
        ],
    )


def allocate(
    amount: Decimal, balances: list[tuple[str, Decimal]]
) -> tuple[list[tuple[str, Decimal]], Decimal]:
    """Apply a payment to open balances in the order given (oldest first). Returns (applied, left over)."""
    if amount < 0:
        raise InvoiceInputError("A payment cannot be negative")
    left = amount
    applied: list[tuple[str, Decimal]] = []
    for key, balance in balances:
        if left <= 0:
            break
        if balance <= 0:
            continue
        part = min(left, balance)
        applied.append((key, part))
        left -= part
    return applied, left
