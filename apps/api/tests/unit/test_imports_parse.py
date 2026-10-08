"""Spreadsheet import helpers: the formats Kenyan agents actually use, and commission arithmetic."""

from datetime import date
from decimal import Decimal

import pytest

from app.calc.commission import commission, withholding
from app.jurisdictions.loader import pack, pack_for_country
from app.modules.imports import parse

KE = pack("ke", "2026.1")
CLASSES = [(c.code, c.name) for c in KE.classes]


def test_read_csv_handles_bom_semicolons_and_blank_lines() -> None:
    headers, rows = parse.read_csv(
        "﻿Insured;Reg No;Expiry\nOtieno Ochieng;KDA 123A;31/12/2026\n;;\n"
    )
    assert headers == ["Insured", "Reg No", "Expiry"]
    assert rows == [{"Insured": "Otieno Ochieng", "Reg No": "KDA 123A", "Expiry": "31/12/2026"}]


@pytest.mark.parametrize(
    ("text", "message"),
    [("", "empty"), ("Name,Name\nA,B\n", "different"), ("Name,\nA,B\n", "heading")],
)
def test_read_csv_rejects_unusable_files(text: str, message: str) -> None:
    with pytest.raises(parse.ImportFileError, match=message):
        parse.read_csv(text)


def test_read_csv_limits_rows() -> None:
    with pytest.raises(parse.ImportFileError, match="up to"):
        parse.read_csv("Name\n" + "A B\n" * (parse.MAX_ROWS + 1))


def test_detect_mapping_from_agent_headings() -> None:
    headers = [
        "Insured Name",
        "Mobile",
        "Insurance Company",
        "Cover Type",
        "Policy No",
        "Reg No",
        "Inception Date",
        "Expiry Date",
        "Gross Premium",
        "Comm %",
        "Notes",
    ]
    mapping = parse.detect_mapping(headers)
    assert mapping == {
        "client_name": "Insured Name",
        "phone": "Mobile",
        "insurer": "Insurance Company",
        "class": "Cover Type",
        "policy_number": "Policy No",
        "description": "Reg No",
        "start_date": "Inception Date",
        "end_date": "Expiry Date",
        "premium": "Gross Premium",
        "commission_rate": "Comm %",
    }
    assert parse.check_mapping(mapping, headers) == []
    assert (
        parse.check_mapping({"client_name": "Nope"}, headers)[0] == "No column 'Nope' in the file"
    )
    assert "Choose the column for Insurer" in parse.check_mapping({}, headers)


@pytest.mark.parametrize(
    "raw",
    [
        "2026-12-31",
        "31/12/2026",
        "31-12-2026",
        "31.12.2026",
        "31/12/26",
        "31 Dec 2026",
        "31-Dec-2026",
    ],
)
def test_parse_date(raw: str) -> None:
    assert parse.parse_date(raw) == date(2026, 12, 31)


def test_parse_date_rejects_us_and_garbage() -> None:
    for raw in ("12/31/2026", "soon"):
        with pytest.raises(ValueError, match="Cannot read the date"):
            parse.parse_date(raw)


def test_amounts_rates_and_paid() -> None:
    assert parse.parse_amount("KES 38,500.50") == Decimal("38500.50")
    assert parse.parse_amount("Ksh. 1 200") == Decimal(1200)
    assert parse.parse_amount("") is None
    with pytest.raises(ValueError, match="amount"):
        parse.parse_amount("-5")
    assert parse.parse_rate("10") == Decimal("0.1")
    assert parse.parse_rate("12.5%") == Decimal("0.125")
    assert parse.parse_rate("0.075") == Decimal("0.075")
    assert parse.parse_rate("") is None
    with pytest.raises(ValueError, match="rate"):
        parse.parse_rate("150%")
    premium = Decimal(38500)
    assert parse.parse_paid("Yes", premium) == premium
    assert parse.parse_paid("no", premium) is None
    assert parse.parse_paid("20,000", premium) == Decimal(20000)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("motor_private", "motor_private"),
        ("Motor private", "motor_private"),
        ("Motor - Comprehensive", "motor_private"),
        ("Third Party Only", "motor_private"),
        ("PSV", "motor_psv"),
        ("Medical", "medical_individual"),
        ("WIBA", "wiba"),
        ("Last expense", "last_expense"),
        ("Space tourism", None),
    ],
)
def test_match_class(raw: str, code: str | None) -> None:
    assert parse.match_class(raw, CLASSES) == code


def test_split_name() -> None:
    assert parse.split_name("otieno  ochieng") == {
        "kind": "individual",
        "first_name": "Otieno",
        "last_name": "Ochieng",
    }
    assert parse.split_name("Mary Wanjiru Kamau")["other_names"] == "Wanjiru"
    assert parse.split_name("Acacia Traders Ltd") == {
        "kind": "corporate",
        "company_name": "Acacia Traders Ltd",
    }
    with pytest.raises(ValueError, match="first and last"):
        parse.split_name("Otieno")


def test_commission_withholds_10_percent_for_resident_agents() -> None:
    c = commission(KE, Decimal(35000), Decimal("0.10"), currency="KES", intermediary="agent")
    assert (c.gross, c.wht, c.vat, c.net) == (
        Decimal("3500.00"),
        Decimal("350.00"),
        Decimal("0.00"),
        Decimal("3150.00"),
    )
    broker = withholding(KE, Decimal(1000), currency="KES", intermediary="broker")
    assert broker.wht == Decimal("50.00")
    assert withholding(
        pack_for_country("UG"), Decimal(1000), currency="UGX", intermediary="agent"
    ).net == Decimal(1000)
