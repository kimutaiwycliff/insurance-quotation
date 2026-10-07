"""Numbering patterns and payment references (pure logic)."""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.numbering.pattern import (
    InvalidPatternError,
    Pattern,
    ResetPeriod,
    period_key,
)
from app.modules.numbering.references import (
    ALPHABET,
    LENGTH,
    generate_payment_reference,
    is_valid_payment_reference,
)

ON = date(2026, 3, 7)


class TestPattern:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("INV-{YYYY}-{SEQ:5}", "INV-2026-00042"),
            ("QT/{YY}{MM}/{SEQ}", "QT/2603/42"),
            ("{BRANCH}-RCT-{SEQ:3}", "NBO-RCT-042"),
            ("{SEQ:1}", "42"),
        ],
    )
    def test_formats(self, raw: str, expected: str) -> None:
        assert Pattern.parse(raw).format(seq=42, on=ON, branch_code="NBO") == expected

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ("", "1-64"),
            ("INV-{YYYY}", "exactly once"),
            ("{SEQ}{SEQ}", "exactly once"),
            ("{FOO}-{SEQ}", "Unknown token"),
            ("{YYYY:2}-{SEQ}", "width"),
            ("{SEQ:0}", "width"),
            ("INV {SEQ}", "Literal"),
            ("<b>{SEQ}", "Literal"),
            ("X" * 65 + "{SEQ}", "1-64"),
        ],
    )
    def test_rejects_invalid(self, raw: str, message: str) -> None:
        with pytest.raises(InvalidPatternError, match=message):
            Pattern.parse(raw)

    def test_branch_token_requires_branch(self) -> None:
        with pytest.raises(InvalidPatternError, match="BRANCH"):
            Pattern.parse("{BRANCH}-{SEQ}").format(seq=1, on=ON)

    def test_sequence_starts_at_one(self) -> None:
        with pytest.raises(ValueError, match="start at 1"):
            Pattern.parse("{SEQ}").format(seq=0, on=ON)

    def test_overlong_result_is_rejected(self) -> None:
        pattern = Pattern.parse("A" * 40 + "{SEQ:9}")
        with pytest.raises(InvalidPatternError, match="exceeds"):
            pattern.format(seq=1, on=ON)

    def test_period_keys(self) -> None:
        assert period_key(ResetPeriod.NEVER, ON) == "all"
        assert period_key(ResetPeriod.YEARLY, ON) == "2026"
        assert period_key(ResetPeriod.MONTHLY, ON) == "2026-03"


class TestPaymentReference:
    def test_shape(self) -> None:
        ref = generate_payment_reference()
        assert len(ref) == LENGTH <= 12  # M-Pesa AccountReference limit
        assert set(ref) <= set(ALPHABET)
        assert is_valid_payment_reference(ref)

    def test_accepts_what_people_type(self) -> None:
        ref = generate_payment_reference()
        assert is_valid_payment_reference(f"{ref[:5].lower()} -{ref[5:]}")

    def test_rejects_bad_input(self) -> None:
        assert not is_valid_payment_reference("")
        assert not is_valid_payment_reference("O0I1L" * 2)
        assert not is_valid_payment_reference(generate_payment_reference() + "2")

    @given(st.data())
    def test_detects_every_adjacent_swap(self, data: st.DataObject) -> None:
        ref = generate_payment_reference()
        pos = data.draw(st.integers(0, LENGTH - 3))
        if ref[pos] != ref[pos + 1]:
            swapped = ref[:pos] + ref[pos + 1] + ref[pos] + ref[pos + 2 :]
            assert not is_valid_payment_reference(swapped)

    @given(st.data())
    def test_detects_every_single_character_error(self, data: st.DataObject) -> None:
        ref = generate_payment_reference()
        pos = data.draw(st.integers(0, LENGTH - 1))
        replacement = data.draw(st.sampled_from([c for c in ALPHABET if c != ref[pos]]))
        assert not is_valid_payment_reference(ref[:pos] + replacement + ref[pos + 1 :])
