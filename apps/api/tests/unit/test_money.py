"""Money: decimal-only arithmetic, ISO 4217 rounding, string wire format."""

from decimal import ROUND_HALF_EVEN, Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core.money import (
    CurrencyMismatchError,
    Money,
    MoneyModel,
    UnknownCurrencyError,
    minor_unit,
)

amounts = st.decimals(
    min_value=Decimal("-1e12"), max_value=Decimal("1e12"), places=4, allow_nan=False
)


class TestMoney:
    def test_rounds_to_minor_unit_per_currency(self) -> None:
        assert Money.of("10.005", "KES").rounded().amount == Decimal("10.01")
        assert Money.of("1500.5", "UGX").rounded().amount == Decimal("1501")
        assert Money.of("1.0005", "KWD").rounded().amount == Decimal("1.001")

    def test_rounded_keeps_minor_unit_exponent(self) -> None:
        assert str(Money.of("100", "KES").rounded().amount) == "100.00"

    def test_rounding_mode_is_selectable(self) -> None:
        assert Money.of("10.005", "KES").rounded(ROUND_HALF_EVEN).amount == Decimal("10.00")

    def test_storage_precision_is_four_places(self) -> None:
        assert Money.of("1.123456", "KES").amount == Decimal("1.1235")

    def test_arithmetic_requires_same_currency(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            _ = Money.of(1, "KES") + Money.of(1, "USD")

    def test_arithmetic(self) -> None:
        total = Money.of("100.10", "KES") + Money.of("0.20", "KES") - Money.of("0.30", "KES")
        assert total == Money.of("100.00", "KES")
        assert (-total).amount == Decimal("-100.00")
        assert Money.of("200", "KES").times(Decimal("0.16")) == Money.of("32", "KES")
        assert Money.zero("KES").is_zero()

    def test_rejects_unknown_currency_and_overflow(self) -> None:
        with pytest.raises(UnknownCurrencyError):
            minor_unit("XXX")
        with pytest.raises(ValueError, match="NUMERIC"):
            Money.of("1e16", "KES")
        with pytest.raises(ValueError, match="valid amount"):
            Money.of("abc", "KES")
        with pytest.raises(ValueError, match="finite"):
            Money.of("Infinity", "KES")

    @given(amounts, amounts)
    def test_addition_is_exact(self, a: Decimal, b: Decimal) -> None:
        assert (Money(a, "KES") + Money(b, "KES")).amount == a + b

    @given(amounts)
    def test_rounding_is_idempotent(self, a: Decimal) -> None:
        once = Money(a, "KES").rounded()
        assert once.rounded() == once


class TestMoneyModel:
    def test_serialises_amount_as_string(self) -> None:
        dumped = MoneyModel(amount=Decimal("1234.50"), currency="KES").model_dump(mode="json")
        assert dumped == {"amount": "1234.50", "currency": "KES"}

    def test_never_uses_exponent_notation(self) -> None:
        model = MoneyModel.model_validate({"amount": "1E+3", "currency": "KES"})
        assert model.model_dump(mode="json")["amount"] == "1000"

    def test_rejects_floats_and_unknown_currencies(self) -> None:
        with pytest.raises(ValidationError, match="strings"):
            MoneyModel.model_validate({"amount": 1.5, "currency": "KES"})
        with pytest.raises(ValidationError):
            MoneyModel.model_validate({"amount": "1", "currency": "XXX"})

    def test_round_trip(self) -> None:
        money = Money.of("99.99", "KES")
        assert money.to_json().to_money() == money
