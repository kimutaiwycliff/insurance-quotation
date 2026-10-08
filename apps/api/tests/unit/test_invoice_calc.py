"""Invoice arithmetic: worked examples (KE VAT 16%) and properties that hold for any input."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.calc.invoice import InvoiceInputError, LineIn, allocate, calculate_invoice
from app.jurisdictions.loader import pack

KE = pack("ke", "2026.1")
D = Decimal


def _line(qty: str, price: str, code: str = "vat_standard", discount: str = "0") -> LineIn:
    return LineIn(quantity=D(qty), unit_price=D(price), tax_code=code, discount_rate=D(discount))


def test_vat_exclusive_with_discount_and_mixed_codes() -> None:
    totals = calculate_invoice(
        KE,
        [_line("3", "1500", discount="0.10"), _line("1", "2000", "exempt")],
        currency="KES",
        prices_include_tax=False,
    )
    first = totals.lines[0]
    assert (first.gross, first.discount, first.net, first.tax, first.total) == (
        D("4500.00"),
        D("450.00"),
        D("4050.00"),
        D("648.00"),
        D("4698.00"),
    )
    assert (totals.subtotal, totals.tax, totals.total) == (D("6050.00"), D("648.00"), D("6698.00"))
    assert [(t.code, t.taxable, t.tax) for t in totals.taxes] == [
        ("vat_standard", D("4050.00"), D("648.00")),
        ("exempt", D("2000.00"), D(0)),
    ]


def test_vat_inclusive_prices_back_out_the_tax() -> None:
    totals = calculate_invoice(KE, [_line("1", "1160")], currency="KES", prices_include_tax=True)
    assert (totals.subtotal, totals.tax, totals.total) == (D("1000.00"), D("160.00"), D("1160.00"))
    odd = calculate_invoice(KE, [_line("1", "999.99")], currency="KES", prices_include_tax=True)
    assert odd.total == D("999.99")
    assert odd.subtotal + odd.tax == odd.total


def test_rejects_empty_and_unknown_codes() -> None:
    with pytest.raises(InvoiceInputError, match="at least one line"):
        calculate_invoice(KE, [], currency="KES", prices_include_tax=False)
    with pytest.raises(InvoiceInputError, match="Unknown tax code"):
        calculate_invoice(KE, [_line("1", "1", "vat_99")], currency="KES", prices_include_tax=False)


def test_allocation_oldest_first_with_credit_left() -> None:
    applied, left = allocate(D(1500), [("a", D(1000)), ("b", D(0)), ("c", D(800))])
    assert applied == [("a", D(1000)), ("c", D(500))]
    assert left == D(0)
    applied, left = allocate(D(2000), [("a", D(1000))])
    assert (applied, left) == ([("a", D(1000))], D(1000))
    with pytest.raises(InvoiceInputError):
        allocate(D(-1), [])


money = st.decimals(min_value=D(0), max_value=D(1_000_000), places=2)
qty = st.decimals(min_value=D("0.01"), max_value=D(1000), places=2)
codes = st.sampled_from(["vat_standard", "exempt", "zero_rated"])


@given(
    st.lists(
        st.tuples(qty, money, codes, st.decimals(min_value=D(0), max_value=D(1), places=2)),
        min_size=1,
        max_size=8,
    ),
    st.booleans(),
)
def test_totals_always_add_up(
    raw: list[tuple[Decimal, Decimal, str, Decimal]], inclusive: bool
) -> None:
    lines = [LineIn(quantity=q, unit_price=p, tax_code=c, discount_rate=r) for q, p, c, r in raw]
    totals = calculate_invoice(KE, lines, currency="KES", prices_include_tax=inclusive)
    assert totals.subtotal + totals.tax == totals.total
    assert sum((t.tax for t in totals.taxes), D(0)) == totals.tax
    for line in totals.lines:
        assert line.net + line.tax == line.total
        assert line.tax >= 0
        assert line.total == line.total.quantize(D("0.01"))  # rounded to cents


@given(money, st.lists(money, max_size=6))
def test_allocation_never_over_applies(amount: Decimal, balances: list[Decimal]) -> None:
    applied, left = allocate(amount, [(str(i), b) for i, b in enumerate(balances)])
    assert sum((a for _, a in applied), D(0)) + left == amount
    for key, part in applied:
        assert 0 < part <= balances[int(key)]
