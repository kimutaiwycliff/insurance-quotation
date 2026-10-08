"""Money and currencies (ADR-0008).

Rules (CLAUDE.md rule 2):

* amounts are :class:`~decimal.Decimal`, never ``float``; Postgres columns are ``NUMERIC(20,4)``;
* JSON carries amounts as strings: ``{"amount": "1234.50", "currency": "KES"}``;
* rounding to a currency's ISO 4217 minor unit happens **only** here (:meth:`Money.rounded`).

Intermediate results keep four decimal places (the column scale); only amounts that are presented or
settled are rounded to the minor unit.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, field_validator

# Storage scale of every money column (NUMERIC(20,4)).
STORAGE_SCALE = 4
_STORAGE_QUANT = Decimal(1).scaleb(-STORAGE_SCALE)
MAX_INTEGER_DIGITS = 16  # NUMERIC(20,4): 16 digits before the point

# Supported currencies and their ISO 4217 minor units. The ``currencies`` table is seeded with exactly
# these rows by migration 0002; an integration test keeps the two in sync.
ISO_4217_MINOR_UNITS: dict[str, int] = {
    "KES": 2,  # Kenya
    "UGX": 0,  # Uganda
    "TZS": 2,  # Tanzania
    "RWF": 0,  # Rwanda
    "BIF": 0,  # Burundi
    "ETB": 2,  # Ethiopia
    "SSP": 2,  # South Sudan
    "NGN": 2,
    "GHS": 2,
    "ZAR": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "AED": 2,
    "INR": 2,
    "JPY": 0,
    "BHD": 3,
    "KWD": 3,
}

CURRENCY_NAMES: dict[str, str] = {
    "KES": "Kenyan shilling",
    "UGX": "Ugandan shilling",
    "TZS": "Tanzanian shilling",
    "RWF": "Rwandan franc",
    "BIF": "Burundian franc",
    "ETB": "Ethiopian birr",
    "SSP": "South Sudanese pound",
    "NGN": "Nigerian naira",
    "GHS": "Ghanaian cedi",
    "ZAR": "South African rand",
    "USD": "US dollar",
    "EUR": "Euro",
    "GBP": "Pound sterling",
    "AED": "UAE dirham",
    "INR": "Indian rupee",
    "JPY": "Japanese yen",
    "BHD": "Bahraini dinar",
    "KWD": "Kuwaiti dinar",
}

# Wide enough for NUMERIC(20,4) arithmetic without silent precision loss.
_CONTEXT = Context(prec=34)


class UnknownCurrencyError(ValueError):
    pass


class CurrencyMismatchError(ValueError):
    pass


def minor_unit(currency: str) -> int:
    try:
        return ISO_4217_MINOR_UNITS[currency]
    except KeyError:
        raise UnknownCurrencyError(f"Unsupported currency: {currency!r}") from None


def to_decimal(value: Decimal | int | str) -> Decimal:
    """Parse an amount without ever going through ``float``."""
    if isinstance(
        value, float
    ):  # pragma: no cover - guarded by the type system, kept as a last line
        raise TypeError("Money amounts must never be floats")
    try:
        result = Decimal(value) if not isinstance(value, Decimal) else value
    except InvalidOperation:
        raise ValueError(f"Not a valid amount: {value!r}") from None
    if not result.is_finite():
        raise ValueError("Amounts must be finite")
    return result


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in a currency. Arithmetic keeps storage precision; :meth:`rounded` presents it."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        minor_unit(self.currency)  # validates the currency code
        amount = to_decimal(self.amount)
        exponent = amount.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -STORAGE_SCALE:
            # More precision than the column holds: round once, at storage scale.
            amount = amount.quantize(_STORAGE_QUANT, rounding=ROUND_HALF_UP)
        if not amount.is_zero() and amount.adjusted() >= MAX_INTEGER_DIGITS:
            raise ValueError("Amount exceeds NUMERIC(20,4)")
        object.__setattr__(self, "amount", amount)

    @classmethod
    def of(cls, amount: Decimal | int | str, currency: str) -> Self:
        return cls(to_decimal(amount), currency)

    @classmethod
    def zero(cls, currency: str) -> Self:
        return cls(Decimal(0), currency)

    def _same_currency(self, other: Money) -> None:
        if other.currency != self.currency:
            raise CurrencyMismatchError(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(_CONTEXT.add(self.amount, other.amount), self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(_CONTEXT.subtract(self.amount, other.amount), self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def times(self, factor: Decimal | int) -> Money:
        """Multiply by a rate or quantity (never a float)."""
        return Money(_CONTEXT.multiply(self.amount, to_decimal(factor)), self.currency)

    def rounded(self, rounding: str = ROUND_HALF_UP) -> Money:
        """Round to the currency's minor unit (e.g. 2 dp for KES, 0 dp for UGX)."""
        quant = Decimal(1).scaleb(-minor_unit(self.currency))
        return Money(self.amount.quantize(quant, rounding=rounding), self.currency)

    def is_zero(self) -> bool:
        return self.amount.is_zero()

    def to_json(self) -> MoneyModel:
        return MoneyModel(amount=self.amount, currency=self.currency)


def _amount_to_str(value: Decimal) -> str:
    # Fixed-point notation: never ``1E+3``.
    return format(value, "f")


def _reject_float(value: object) -> object:
    if isinstance(value, float):
        msg = 'send amounts and rates as strings (e.g. "1234.50"), not numbers'
        raise ValueError(msg)  # noqa: TRY004 - pydantic turns ValueError (not TypeError) into a 422
    return value


NoFloat = BeforeValidator(_reject_float)

AmountStr = Annotated[
    Decimal,
    NoFloat,
    PlainSerializer(_amount_to_str, return_type=str, when_used="always"),
    Field(json_schema_extra={"type": "string", "pattern": r"^-?\d{1,16}(\.\d{1,4})?$"}),
]


class MoneyModel(BaseModel):
    """Wire format of money: ``{"amount": "1234.50", "currency": "KES"}``."""

    model_config = ConfigDict(frozen=True)

    amount: AmountStr = Field(examples=["1234.50"])
    currency: str = Field(min_length=3, max_length=3, examples=["KES"])

    @field_validator("amount", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("amounts must be sent as strings, not numbers")  # noqa: TRY004 - pydantic needs ValueError
        return value

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        minor_unit(value)
        return value

    def to_money(self) -> Money:
        return Money(self.amount, self.currency)
