"""Premium engine: golden scenarios (KE pack) and properties that must hold for any input."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from app.calc.pack import Pack
from app.calc.premium import (
    Adjustment,
    Benefit,
    PremiumInputError,
    PremiumRequest,
    Rating,
    calculate,
)
from app.jurisdictions.loader import UnknownPackError, all_packs, pack, pack_for_country

GOLDEN = yaml.safe_load((Path(__file__).parent.parent / "golden" / "ke_premium.yaml").read_text())
KE = pack("ke", GOLDEN["version"])


def _request(raw: dict[str, Any]) -> PremiumRequest:
    return PremiumRequest.model_validate({"currency": "KES", "on": date(2026, 10, 8), **raw})


@pytest.mark.parametrize(
    "scenario", GOLDEN["scenarios"], ids=[s["name"] for s in GOLDEN["scenarios"]]
)
def test_golden_scenarios(scenario: dict[str, Any]) -> None:
    result = calculate(KE, _request(scenario["request"]))
    expect = scenario["expect"]
    lines = {line.code: line.amount for line in result.lines}
    if "client_total" in expect:
        assert result.client_total == Decimal(expect["client_total"]), scenario["why"]
    if "insurer_borne" in expect:
        assert result.insurer_borne == Decimal(expect["insurer_borne"])
    for code, amount in expect.get("lines", {}).items():
        assert lines.get(code) == Decimal(amount), (code, scenario["why"])
    for code in expect.get("absent", []):
        assert code not in lines
    if "needs_input" in expect:
        assert result.needs_input == expect["needs_input"]
    for key, amount in expect.get("commission", {}).items():
        assert result.commission is not None
        assert getattr(result.commission, key) == Decimal(amount), key


def test_every_line_cites_its_rule() -> None:
    result = calculate(KE, _request(GOLDEN["scenarios"][0]["request"]))
    statutory = [line for line in result.lines if line.kind in {"levy", "stamp_duty"}]
    assert statutory
    assert all(
        line.rule_id and line.rule_id.endswith("@2026.1") and line.source for line in statutory
    )
    assert result.pack.signed is False
    assert any("pending adviser sign-off" in note for note in result.notes)


def test_rules_not_yet_in_force_do_not_apply() -> None:
    old = _request(
        {
            "class_code": "motor_private",
            "on": "2009-01-01",
            "rating": {"basis": "flat", "flat_amount": "10000"},
        }
    )
    lines = {line.code for line in calculate(KE, old).lines}
    assert "ke.pcf_levy" not in lines  # PCF levy starts 2010-07-01 in this pack
    assert "ke.training_levy" in lines


@pytest.mark.parametrize(
    "rating",
    [
        {"basis": "rate_on_sum_insured", "rate": "0.04"},
        {"basis": "flat"},
        {"basis": "per_member"},
        {"basis": "manual"},
    ],
)
def test_incomplete_ratings_are_rejected(rating: dict[str, str]) -> None:
    with pytest.raises(PremiumInputError):
        calculate(KE, _request({"class_code": "motor_private", "rating": rating}))


def test_unknown_class() -> None:
    with pytest.raises(PremiumInputError, match="Unknown class"):
        calculate(
            KE,
            _request(
                {"class_code": "space_tourism", "rating": {"basis": "flat", "flat_amount": "1"}}
            ),
        )


def test_generic_pack_has_no_statutory_lines() -> None:
    generic = pack("generic")
    result = calculate(
        generic,
        PremiumRequest(
            class_code="home",
            currency="USD",
            on=date(2026, 1, 1),
            rating=Rating(basis="flat", flat_amount=Decimal(1000)),
        ),
    )
    assert result.client_total == Decimal("1000.00")
    assert [line.kind for line in result.lines] == ["premium"]


def test_pack_lookup() -> None:
    assert pack_for_country("KE").code == "ke"
    assert pack_for_country("UG").code == "generic"
    with pytest.raises(UnknownPackError):
        pack("ke", "1999.1")
    assert ("ke", "2026.1") in all_packs()


def test_pack_validation_rejects_inconsistencies() -> None:
    raw = KE.model_dump(mode="json")
    raw["levies"].append(raw["levies"][0])
    with pytest.raises(ValueError, match="unique"):
        Pack.model_validate(raw)
    raw = KE.model_dump(mode="json")
    raw["premium_tax_code"] = "nope"
    with pytest.raises(ValueError, match="Unknown tax code"):
        Pack.model_validate(raw)


amounts = st.decimals(
    min_value=Decimal(0), max_value=Decimal("100000000"), places=2, allow_nan=False
)
rates = st.decimals(min_value=Decimal(0), max_value=Decimal("0.2"), places=4, allow_nan=False)
classes = st.sampled_from([c.code for c in KE.classes])


@given(classes, amounts, rates, rates, st.booleans())
def test_properties(
    class_code: str, sum_insured: Decimal, rate: Decimal, discount: Decimal, cover_note: bool
) -> None:
    request = PremiumRequest(
        class_code=class_code,
        currency="KES",
        on=date(2026, 10, 8),
        document_kind="cover_note" if cover_note else "policy",
        rating=Rating(basis="rate_on_sum_insured", sum_insured=sum_insured, rate=rate),
        min_premium=Decimal(1000),
        benefits=[
            Benefit(code="b", name="Benefit", basis="rate_on_premium", value=Decimal("0.05"))
        ],
        adjustments=[Adjustment(name="Discount", kind="discount", basis="percent", value=discount)],
        stamp_duty_manual=Decimal(5),
        commission_rate=Decimal("0.1"),
    )
    result = calculate(KE, request)
    client = [line for line in result.lines if line.charged_to == "client"]
    assert result.client_total == sum((line.amount for line in client), Decimal(0))
    assert result.adjusted_premium >= Decimal(1000)  # never below the minimum
    assert all(
        line.amount >= 0
        for line in result.lines
        if line.kind in {"levy", "stamp_duty", "fee", "fee_tax"}
    )
    assert all(
        line.amount == line.amount.quantize(Decimal("0.01")) for line in result.lines
    )  # KES minor unit
    assert not any(
        line.code == "ke.pcf_levy_insurer" for line in client
    )  # insurer-borne never billed
    assert result.commission is not None
    assert result.commission.gross <= result.commission.base
    assert result.commission.net == result.commission.gross - result.commission.wht
    if cover_note:
        assert not any(line.kind == "stamp_duty" for line in result.lines)
