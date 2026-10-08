"""Pure helpers for importing an agent's book from a spreadsheet saved as CSV.

Agents keep their book in spreadsheets with their own headings ("Insured", "Reg No", "Expiry"), Kenyan date
formats (31/12/2026) and amounts written as "KES 38,500". These helpers read such files without guessing
silently: anything ambiguous becomes a row error the agent sees before anything is saved.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_ROWS = 1000


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    label: str
    required: bool
    synonyms: tuple[str, ...]


FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "client_name",
        "Client name",
        True,
        (
            "client",
            "client name",
            "name",
            "insured",
            "insured name",
            "policyholder",
            "policy holder",
            "customer",
            "customer name",
        ),
    ),
    FieldSpec(
        "phone",
        "Phone",
        False,
        ("phone", "mobile", "phone number", "mobile number", "tel", "telephone", "cell", "contact"),
    ),
    FieldSpec("email", "Email", False, ("email", "e mail", "email address")),
    FieldSpec("kra_pin", "KRA PIN", False, ("kra pin", "pin", "kra", "pin number")),
    FieldSpec(
        "id_number",
        "ID number",
        False,
        ("id", "id number", "id no", "national id", "id passport", "passport"),
    ),
    FieldSpec(
        "insurer",
        "Insurer",
        True,
        ("insurer", "insurance company", "underwriter", "company", "insurance", "insurer name"),
    ),
    FieldSpec(
        "class",
        "Class of business",
        True,
        (
            "class",
            "class of business",
            "cover",
            "cover type",
            "type",
            "type of cover",
            "product",
            "line",
        ),
    ),
    FieldSpec(
        "policy_number",
        "Policy number",
        False,
        ("policy number", "policy no", "policy", "pol no", "policy num"),
    ),
    FieldSpec(
        "description",
        "What is covered",
        False,
        (
            "description",
            "vehicle",
            "reg",
            "reg no",
            "registration",
            "vehicle reg",
            "risk",
            "details",
            "item",
            "subject matter",
        ),
    ),
    FieldSpec(
        "start_date",
        "Cover starts",
        True,
        (
            "start",
            "start date",
            "inception",
            "inception date",
            "from",
            "cover start",
            "commencement",
            "effective date",
        ),
    ),
    FieldSpec(
        "end_date",
        "Cover ends",
        False,
        (
            "end",
            "end date",
            "expiry",
            "expiry date",
            "to",
            "renewal date",
            "cover end",
            "expires",
            "due date",
        ),
    ),
    FieldSpec(
        "premium",
        "Total premium",
        True,
        ("premium", "total premium", "gross premium", "amount", "premium payable"),
    ),
    FieldSpec(
        "sum_insured",
        "Sum insured",
        False,
        ("sum insured", "value", "sum assured", "vehicle value", "insured value"),
    ),
    FieldSpec("paid", "Premium paid", False, ("paid", "amount paid", "premium paid", "payment")),
    FieldSpec(
        "commission_rate",
        "Commission rate",
        False,
        ("commission", "commission rate", "comm", "comm rate", "commission percent"),
    ),
    FieldSpec(
        "basic_premium",
        "Premium before levies",
        False,
        ("basic premium", "net premium", "premium before levies", "basic"),
    ),
)

_FIELD_KEYS = {f.key for f in FIELDS}
_CORPORATE = re.compile(
    r"\b(ltd|limited|company|co\.?|plc|sacco|group|enterprises?|investments?|holdings|school|church|"
    r"association|foundation|trust|bank|hospital|agencies|services)\b",
    re.IGNORECASE,
)
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d %b %Y",
    "%d %B %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
)
# Common words for classes in Kenyan books → words to look for in the pack's class names.
_CLASS_HINTS: tuple[tuple[str, str], ...] = (
    ("third party", "motor private"),
    ("tpo", "motor private"),
    ("comprehensive", "motor private"),
    ("psv", "motor psv"),
    ("matatu", "motor psv"),
    ("commercial", "motor commercial"),
    ("boda", "motorcycle"),
    ("motorcycle", "motorcycle"),
    ("motor", "motor private"),
    ("health", "medical (individual"),
    ("medical", "medical (individual"),
    ("inpatient", "medical (individual"),
    ("domestic", "home"),
    ("household", "home"),
    ("pa", "personal accident"),
    ("funeral", "last expense"),
    ("last expense", "last expense"),
    ("education", "education"),
    ("life", "term life"),
)


class ImportFileError(ValueError):
    pass


def normalise_header(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def read_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Headers and rows (as dicts keyed by header). Accepts comma, semicolon or tab separators and a BOM."""
    text = text.lstrip("﻿")
    if not text.strip():
        raise ImportFileError("The file is empty")
    sample = text[:4096]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        raise ImportFileError("The file is empty")
    headers = [h.strip() for h in rows[0]]
    if len(set(headers)) != len(headers) or any(not h for h in headers):
        raise ImportFileError("Every column needs a heading, and headings must be different")
    body = rows[1:]
    if len(body) > MAX_ROWS:
        raise ImportFileError(f"Import up to {MAX_ROWS} rows at a time; split the file")
    return headers, [
        {h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(headers)} for r in body
    ]


def detect_mapping(headers: list[str]) -> dict[str, str]:
    """Field → column, by exact match on known headings (first match wins; a column is used once)."""
    used: set[str] = set()
    mapping: dict[str, str] = {}
    normalised = {h: normalise_header(h) for h in headers}
    for spec in FIELDS:
        for synonym in spec.synonyms:
            column = next(
                (h for h, n in normalised.items() if n == synonym and h not in used), None
            )
            if column is not None:
                mapping[spec.key] = column
                used.add(column)
                break
    return mapping


def check_mapping(mapping: dict[str, str], headers: list[str]) -> list[str]:
    problems = [f"Unknown field {k!r}" for k in mapping if k not in _FIELD_KEYS]
    problems += [f"No column {v!r} in the file" for v in mapping.values() if v not in headers]
    problems += [
        f"Choose the column for {f.label}" for f in FIELDS if f.required and f.key not in mapping
    ]
    if len(set(mapping.values())) != len(mapping):
        problems.append("Each column can be used for one field only")
    return problems


def parse_date(value: str) -> date:
    raw = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()  # noqa: DTZ007 - a calendar date, no time
        except ValueError:
            continue
    raise ValueError(f"Cannot read the date {raw!r}; use 31/12/2026 or 2026-12-31")


def parse_amount(value: str) -> Decimal | None:
    raw = re.sub(r"(?i)\b(kes|kshs?|ksh)\b\.?", "", value).replace(",", "").replace(" ", "").strip()
    if not raw or raw in {"-", "0.00-"}:
        return None
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"Cannot read the amount {value!r}") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"Cannot read the amount {value!r}")
    return amount


def parse_rate(value: str) -> Decimal | None:
    """Commission rate as a fraction: "10", "10%" and "0.1" all mean 10%."""
    raw = value.strip()
    if not raw:
        return None
    percent = raw.endswith("%")
    try:
        number = Decimal(raw.rstrip("%").strip())
    except InvalidOperation:
        raise ValueError(f"Cannot read the commission rate {value!r}") from None
    fraction = number / 100 if percent or number >= 1 else number
    if not Decimal(0) <= fraction <= 1:
        raise ValueError(f"Cannot read the commission rate {value!r}")
    return fraction


def parse_paid(value: str, premium: Decimal) -> Decimal | None:
    """ "yes"/"paid" → the premium; "no"/"" → nothing; an amount → that amount."""
    raw = value.strip().lower()
    if raw in {"", "no", "n", "unpaid", "false", "0", "none", "pending"}:
        return None
    if raw in {"yes", "y", "paid", "true", "full", "fully paid", "x"}:
        return premium
    return parse_amount(value)


def match_class(value: str, classes: list[tuple[str, str]]) -> str | None:
    """The pack class code for what the agent wrote ("Motor - Comprehensive", "medical_individual"...)."""
    raw = normalise_header(value)
    if not raw:
        return None
    for code, name in classes:
        if raw in {code.replace("_", " "), normalise_header(name)}:
            return code
    for code, name in classes:
        if normalise_header(name).startswith(raw):
            return code
    for hint, target in _CLASS_HINTS:
        if re.search(rf"\b{re.escape(hint)}\b", raw):
            match = next((c for c, n in classes if n.lower().startswith(target)), None)
            if match:
                return match
    return None


def split_name(name: str) -> dict[str, str]:
    """Client fields from a name: companies by their suffix, people as first + last (+ other names)."""
    clean = re.sub(r"\s+", " ", name).strip()
    if _CORPORATE.search(clean):
        return {"kind": "corporate", "company_name": clean}
    parts = clean.split(" ")
    if len(parts) < 2:  # noqa: PLR2004
        raise ValueError("Give the client's first and last name")
    out = {"kind": "individual", "first_name": parts[0].title(), "last_name": parts[-1].title()}
    if len(parts) > 2:  # noqa: PLR2004
        out["other_names"] = " ".join(p.title() for p in parts[1:-1])
    return out
