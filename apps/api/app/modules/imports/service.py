"""Import an agent's existing book (clients and policies) from a spreadsheet saved as CSV (Plan A1.1 R1.5).

The same planning step serves the preview and the import, so what the agent previews is exactly what is
saved. Clients are matched on phone, email or KRA PIN (within the file and against the book) before new ones
are created. A policy whose insurer and number are already in the book is skipped. Imported policies are
existing cover, so they are recorded as active with activation basis ``imported`` (ADR-0019) and a link to the
import log. Without a "paid" column, ``assume_paid`` records the premium as paid to the insurer on the start
date ("Opening balance (import)").

Everything happens in one transaction: a failure saves nothing.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from http import HTTPStatus
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError, PermissionDeniedError
from app.core.permissions import Perm
from app.core.phone import InvalidPhoneError, to_e164
from app.modules.clients import service as clients
from app.modules.imports import parse
from app.modules.imports.models import BookImport
from app.modules.imports.schemas import (
    FieldInfo,
    ImportPreview,
    ImportRequest,
    ImportResult,
    RowResult,
)
from app.modules.insurers import service as insurers
from app.modules.policies import service as policies
from app.platform import audit
from app.platform.deps import TenantContext


class ImportInvalidError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "import_invalid"
    title = "The file cannot be imported as it is"


@dataclass
class _Row:
    line: int
    values: dict[str, str]
    messages: list[str] = field(default_factory=list)
    status: str = "ok"
    client_key: str = ""
    client_fields: dict[str, Any] = field(default_factory=dict)
    client_id: uuid.UUID | None = None
    class_code: str | None = None
    start: date | None = None
    end: date | None = None
    premium: Decimal | None = None
    paid: Decimal | None = None
    sum_insured: Decimal | None = None
    rate: Decimal | None = None
    base: Decimal | None = None

    def error(self, message: str) -> None:
        self.messages.append(message)
        self.status = "error"


@dataclass
class _Plan:
    headers: list[str]
    mapping: dict[str, str]
    problems: list[str]
    rows: list[_Row]
    matched: dict[str, uuid.UUID]  # client key → existing client


def _value(row: dict[str, str], mapping: dict[str, str], key: str) -> str:
    column = mapping.get(key)
    return row.get(column, "").strip() if column else ""


def _parse_client(row: _Row, v: dict[str, str]) -> None:
    try:
        row.client_fields = parse.split_name(v["client_name"]) if v["client_name"] else {}
    except ValueError as exc:
        row.error(str(exc))
    if not v["client_name"]:
        row.error("The client's name is missing")
    phone = None
    if v["phone"]:
        try:
            phone = to_e164(v["phone"])
        except InvalidPhoneError:
            row.error(f"Cannot read the phone number {v['phone']!r}")
    contact = {
        "phone": phone,
        "email": v["email"].lower() or None,
        "kra_pin": v["kra_pin"].upper() or None,
        "id_number": v["id_number"] or None,
    }
    row.client_fields |= {k: val for k, val in contact.items() if val}
    row.client_key = phone or contact["email"] or contact["kra_pin"] or v["client_name"].lower()


def _parse_cover(row: _Row, v: dict[str, str], classes: list[tuple[str, str]]) -> None:
    if not v["insurer"]:
        row.error("The insurer is missing")
    row.class_code = parse.match_class(v["class"], classes)
    if row.class_code is None:
        row.error(f"Unknown class of business {v['class']!r}; use a name from the list")
    if not v["start_date"]:
        row.error("The start date is missing")
    try:
        row.start = parse.parse_date(v["start_date"]) if v["start_date"] else None
        row.end = parse.parse_date(v["end_date"]) if v["end_date"] else None
    except ValueError as exc:
        row.error(str(exc))
    if row.start and row.end and row.end <= row.start:
        row.error("The end date must be after the start date")


def _parse_money(row: _Row, v: dict[str, str], has_paid: bool, assume_paid: bool) -> None:
    try:
        row.premium = parse.parse_amount(v["premium"])
        row.sum_insured = parse.parse_amount(v["sum_insured"])
        row.base = parse.parse_amount(v["basic_premium"])
        row.rate = parse.parse_rate(v["commission_rate"])
        if row.premium is not None:
            row.paid = (
                parse.parse_paid(v["paid"], row.premium)
                if has_paid
                else (row.premium if assume_paid else None)
            )
    except ValueError as exc:
        row.error(str(exc))
    if row.premium is None and not any(m.startswith("Cannot read") for m in row.messages):
        row.error("The premium is missing")
    if row.rate is not None and row.base is None and row.status == "ok":
        row.messages.append("Commission not set: add the premium before levies to work it out")
        row.rate = None


def _parse_row(
    row: _Row, mapping: dict[str, str], classes: list[tuple[str, str]], assume_paid: bool
) -> None:
    v = {f.key: _value(row.values, mapping, f.key) for f in parse.FIELDS}
    _parse_client(row, v)
    _parse_cover(row, v, classes)
    _parse_money(row, v, "paid" in mapping, assume_paid)


async def _plan(ctx: TenantContext, body: ImportRequest, settings: Settings) -> _Plan:
    try:
        headers, raw_rows = parse.read_csv(body.csv)
    except parse.ImportFileError as exc:
        raise ImportInvalidError(str(exc)) from None
    mapping = body.mapping if body.mapping is not None else parse.detect_mapping(headers)
    problems = parse.check_mapping(mapping, headers)
    pack, _, _ = await insurers.agency_pack(ctx)
    classes = [(c.code, c.name) for c in pack.classes]
    rows = [_Row(line=i + 2, values=r) for i, r in enumerate(raw_rows)]
    if problems:
        return _Plan(headers, mapping, problems, rows, {})
    existing = await policies.existing_numbers(ctx)
    seen_numbers: set[tuple[str, str]] = set()
    matched: dict[str, uuid.UUID] = {}
    checked: set[str] = set()
    for row in rows:
        _parse_row(row, mapping, classes, body.assume_paid)
        number = _value(row.values, mapping, "policy_number")
        insurer = _value(row.values, mapping, "insurer")
        key = (insurer.lower(), number.lower())
        if number and key in existing and row.status == "ok":
            row.status = "skip"
            row.messages.append("Already in your book (same insurer and policy number)")
        elif number and key in seen_numbers and row.status == "ok":
            row.status = "skip"
            row.messages.append("Appears twice in the file")
        if number:
            seen_numbers.add(key)
        if row.status != "ok" or row.client_key in checked:
            continue
        checked.add(row.client_key)
        f = row.client_fields
        if not any(f.get(k) for k in ("phone", "email", "kra_pin", "id_number")):
            continue
        try:
            check = clients.DuplicateCheck(
                phone=f.get("phone"),
                email=f.get("email"),
                kra_pin=f.get("kra_pin"),
                id_number=f.get("id_number"),
            )
        except ValidationError:
            row.error("Check the client's email address")
            continue
        found = await clients.find_duplicates(ctx, check, settings)
        if found.matches:
            matched[row.client_key] = found.matches[0].client.id
        elif found.hidden:
            row.error("This client is in another agent's book; ask them or an admin to import it")
    return _Plan(headers, mapping, [], rows, matched)


def _preview(plan: _Plan) -> ImportPreview:
    results: list[RowResult] = []
    new_keys: set[str] = set()
    for row in plan.rows:
        action = None
        if row.status == "ok":
            action = "match" if row.client_key in plan.matched else "create"
            if action == "create":
                new_keys.add(row.client_key)
        results.append(
            RowResult(
                line=row.line,
                status=row.status,  # type: ignore[arg-type]
                messages=row.messages,
                client_name=_value(row.values, plan.mapping, "client_name"),
                client_action=action,  # type: ignore[arg-type]
                insurer=_value(row.values, plan.mapping, "insurer"),
                class_code=row.class_code,
                policy_number=_value(row.values, plan.mapping, "policy_number") or None,
                description=_value(row.values, plan.mapping, "description"),
                start_date=row.start,
                end_date=row.end,
                premium=row.premium,
                paid=row.paid,
            )
        )
    ok = [r for r in results if r.status == "ok"]
    return ImportPreview(
        columns=plan.headers,
        mapping=plan.mapping,
        fields=[FieldInfo(key=f.key, label=f.label, required=f.required) for f in parse.FIELDS],
        problems=plan.problems,
        rows=results,
        ok=len(ok),
        errors=sum(1 for r in results if r.status == "error"),
        skipped=sum(1 for r in results if r.status == "skip"),
        new_clients=len(new_keys),
        matched_clients=len(
            {r.client_key for r in plan.rows if r.status == "ok"} & set(plan.matched)
        ),
    )


async def preview(ctx: TenantContext, body: ImportRequest, settings: Settings) -> ImportPreview:
    return _preview(await _plan(ctx, body, settings))


async def run_import(ctx: TenantContext, body: ImportRequest, settings: Settings) -> ImportResult:
    plan = await _plan(ctx, body, settings)
    summary = _preview(plan)
    if plan.problems:
        raise ImportInvalidError("; ".join(plan.problems))
    if summary.errors and not body.skip_errors:
        raise ImportInvalidError(
            f"{summary.errors} rows have errors: fix them, or import the other rows only"
        )
    if summary.ok == 0:
        raise ImportInvalidError("There is nothing new to import")
    if any(r.paid for r in plan.rows if r.status == "ok") and (
        Perm.PREMIUM_WRITE not in ctx.principal.permissions
    ):
        raise PermissionDeniedError("Recording premium payments needs the premium:write permission")
    import_id = uuid.uuid7()
    clients_created = 0
    client_ids = dict(plan.matched)
    created = 0
    for row in (r for r in plan.rows if r.status == "ok"):
        if row.client_key not in client_ids:
            client = await clients.create_client(
                ctx,
                clients.ClientCreate.model_validate(
                    {**row.client_fields, "allow_duplicate": True, "source": "other"}
                ),
                settings,
            )
            client_ids[row.client_key] = client.id
            clients_created += 1
        assert row.start is not None  # noqa: S101 - planned rows are complete
        assert row.premium is not None  # noqa: S101
        description = _value(row.values, plan.mapping, "description")
        await policies.create_policy(
            ctx,
            policies.PolicyCreate(
                client_id=client_ids[row.client_key],
                insurer_name=_value(row.values, plan.mapping, "insurer"),
                class_code=row.class_code,
                description=description or None,
                details=[{"label": "Covered", "value": description}] if description else None,  # type: ignore[list-item]
                policy_number=_value(row.values, plan.mapping, "policy_number") or None,
                start_date=row.start,
                end_date=row.end,
                total_premium=row.premium,
                sum_insured=row.sum_insured,
                commission_rate=row.rate,
                commission_base=row.base if row.rate is not None else None,
                payment=policies.PaymentIn(
                    amount=row.paid,
                    paid_on=row.start,
                    method="other",
                    reference="Opening balance (import)",
                    paid_to="insurer",
                )
                if row.paid
                else None,
            ),
            imported=str(import_id),
        )
        created += 1
    ctx.session.add(
        BookImport(
            id=import_id,
            tenant_id=ctx.tenant_id,
            filename=body.filename,
            rows=len(plan.rows),
            clients_created=clients_created,
            clients_matched=summary.matched_clients,
            policies_created=created,
            rows_skipped=summary.errors + summary.skipped,
            options={"mapping": plan.mapping, "assume_paid": body.assume_paid},
            created_by=ctx.principal.user_id,
        )
    )
    await audit.record(
        ctx,
        "book.imported",
        entity_type="book_import",
        entity_id=import_id,
        changes={"policies": created, "clients": clients_created, "file": body.filename},
    )
    await ctx.session.flush()
    return ImportResult(
        import_id=import_id,
        clients_created=clients_created,
        clients_matched=summary.matched_clients,
        policies_created=created,
        rows_skipped=summary.errors + summary.skipped,
    )
