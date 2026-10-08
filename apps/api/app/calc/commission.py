"""Commission arithmetic (pure): gross on the commissionable premium, WHT withheld by the insurer, VAT per pack.

KE (SPEC_REVIEW §2): commission is VAT-exempt; insurers withhold 10% from resident agents (5% brokers, 20%
non-residents). The rates come from the jurisdiction pack, never from code.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.calc.pack import IntermediaryType, Pack
from app.core.money import Money


class Commission(BaseModel):
    model_config = ConfigDict(frozen=True)

    base: Decimal
    rate: Decimal
    gross: Decimal
    wht_rate: Decimal
    wht: Decimal
    vat: Decimal
    net: Decimal


class Withholding(BaseModel):
    """What the insurer pays on a gross commission: WHT withheld and the net amount."""

    model_config = ConfigDict(frozen=True)

    gross: Decimal
    wht_rate: Decimal
    wht: Decimal
    vat: Decimal
    net: Decimal


def _round(pack: Pack, amount: Decimal, currency: str) -> Decimal:
    return Money(amount, currency).rounded(pack.rounding).amount


def withholding(
    pack: Pack, gross: Decimal, *, currency: str, intermediary: IntermediaryType
) -> Withholding:
    gross = _round(pack, gross, currency)
    wht_rate = pack.wht_on_commission.get(intermediary, Decimal(0))
    wht = _round(pack, gross * wht_rate, currency)
    vat = _round(pack, gross * pack.tax(pack.commission_tax_code).rate, currency)
    return Withholding(gross=gross, wht_rate=wht_rate, wht=wht, vat=vat, net=gross - wht + vat)


def commission(
    pack: Pack,
    base: Decimal,
    rate: Decimal,
    *,
    currency: str,
    intermediary: IntermediaryType,
) -> Commission:
    w = withholding(pack, base * rate, currency=currency, intermediary=intermediary)
    return Commission(
        base=base, rate=rate, gross=w.gross, wht_rate=w.wht_rate, wht=w.wht, vat=w.vat, net=w.net
    )
