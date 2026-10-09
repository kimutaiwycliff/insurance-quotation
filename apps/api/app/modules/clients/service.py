"""Clients service: the agency's book of clients, households, contacts, activities and the 360° timeline.

Record-level scoping (ADR-0007): members with ``client:read:all`` see every client; others see only clients
they own. Invisible clients behave as if they did not exist (404). ID numbers are encrypted (ADR-0018) and
only revealed through an audited call.
"""

import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.concurrency import check_version
from app.core.config import Settings
from app.core.crypto import mask, pii_cipher
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.permissions import Perm
from app.core.phone import InvalidPhoneError, to_e164
from app.modules.clients.models import Activity, Client, ClientContact, Household
from app.modules.clients.schemas import (
    ActivityIn,
    ClientCreate,
    ClientSummary,
    ClientUpdate,
    ContactIn,
    DuplicateCheck,
    DuplicateMatch,
    DuplicateResult,
    HouseholdIn,
    TimelineItem,
)
from app.modules.subscriptions import service as subscriptions
from app.modules.tenancy import service as tenancy
from app.platform import audit
from app.platform.deps import TenantContext, own_scope

__all__ = [
    "ActivityIn",
    "Client",
    "ClientCreate",
    "DuplicateCheck",
    "add_activity",
    "create_client",
    "display_name",
    "find_duplicates",
    "get_visible_client",
]


class PossibleDuplicateError(ConflictError):
    code = "possible_duplicate"
    title = "A client with the same phone, email, KRA PIN or ID already exists"


class InvalidOwnerError(AppError):
    status = HTTPStatus.UNPROCESSABLE_CONTENT
    code = "invalid_owner"
    title = "The owner must be an active member of the agency"


MIN_SEARCH_DIGITS = 6  # below this, digits are treated as part of a name


def display_name(kind: str, first: str | None, last: str | None, company: str | None) -> str:
    if kind == "corporate":
        return (company or "").strip()
    return " ".join(p for p in (first, last) if p).strip()


def _scoped[*Ts](stmt: Select[*Ts], ctx: TenantContext) -> Select[*Ts]:
    owner = own_scope(ctx.principal, Perm.CLIENT_READ_ALL)
    return stmt if owner is None else stmt.where(Client.owner_user_id == owner)


async def get_visible_client(ctx: TenantContext, client_id: uuid.UUID) -> Client:
    client = (
        await ctx.session.scalars(_scoped(select(Client).where(Client.id == client_id), ctx))
    ).first()
    if client is None:
        raise NotFoundError("Client not found")
    return client


async def _check_owner(ctx: TenantContext, owner: str) -> None:
    if owner == ctx.principal.user_id:
        return
    if Perm.CLIENT_READ_ALL not in ctx.principal.permissions:
        raise PermissionDeniedError("You can only assign clients to yourself")
    active = {
        m.auth_user_id for m in await tenancy.list_members(ctx.session) if m.status == "active"
    }
    if owner not in active:
        raise InvalidOwnerError()


# ---------------------------------------------------------------- duplicates


async def find_duplicates(
    ctx: TenantContext, check: DuplicateCheck, settings: Settings
) -> DuplicateResult:
    cipher = pii_cipher(settings)
    criteria: list[tuple[str, Any]] = []
    if check.phone:
        criteria.append(
            ("phone", or_(Client.phone == check.phone, Client.alt_phone == check.phone))
        )
    if check.email:
        criteria.append(("email", Client.email == str(check.email)))
    if check.kra_pin:
        criteria.append(("kra_pin", Client.kra_pin == check.kra_pin.upper()))
    if check.id_number:
        criteria.append(("id_number", Client.id_number_hash == cipher.lookup_hash(check.id_number)))
    if not criteria:
        return DuplicateResult(matches=[], hidden=0)
    stmt = select(Client).where(or_(*(c for _, c in criteria)), Client.status == "active").limit(20)
    if check.exclude_id is not None:
        stmt = stmt.where(Client.id != check.exclude_id)
    rows = list((await ctx.session.scalars(stmt)).all())
    owner = own_scope(ctx.principal, Perm.CLIENT_READ_ALL)
    matches, hidden = [], 0
    hashed = cipher.lookup_hash(check.id_number) if check.id_number else None
    for row in rows:
        if owner is not None and row.owner_user_id != owner:
            hidden += 1
            continue
        on = []
        if check.phone and check.phone in (row.phone, row.alt_phone):
            on.append("phone")
        if check.email and row.email and row.email.lower() == str(check.email).lower():
            on.append("email")
        if check.kra_pin and row.kra_pin == check.kra_pin.upper():
            on.append("kra_pin")
        if hashed and row.id_number_hash == hashed:
            on.append("id_number")
        matches.append(DuplicateMatch(client=ClientSummary.model_validate(row), matched_on=on))  # type: ignore[arg-type]
    return DuplicateResult(matches=matches, hidden=hidden)


# ---------------------------------------------------------------- create / update


def _apply_identity(client: Client, data: dict[str, Any], settings: Settings) -> None:
    if "id_number" not in data:
        return
    value = data.pop("id_number")
    if value:
        cipher = pii_cipher(settings)
        client.id_number_enc = cipher.encrypt(value)
        client.id_number_hash = cipher.lookup_hash(value)
        client.id_number_hint = mask(value)
    else:
        client.id_number_enc = client.id_number_hash = client.id_number_hint = None


async def _check_links(ctx: TenantContext, data: dict[str, Any]) -> None:
    if data.get("household_id") and await ctx.session.get(Household, data["household_id"]) is None:
        raise NotFoundError("Household not found")
    if data.get("referred_by_id"):
        await get_visible_client(ctx, data["referred_by_id"])


async def create_client(ctx: TenantContext, body: ClientCreate, settings: Settings) -> Client:
    active = await ctx.session.scalar(
        select(func.count()).select_from(Client).where(Client.status == "active")
    )
    await subscriptions.check_limit(
        ctx.session, ctx.tenant_id, subscriptions.Limit.CLIENTS, int(active or 0)
    )
    data = body.model_dump(exclude_unset=True, exclude={"allow_duplicate"})
    data["kind"] = body.kind
    owner = data.pop("owner_user_id", None) or ctx.principal.user_id
    await _check_owner(ctx, owner)
    await _check_links(ctx, data)
    if not body.allow_duplicate:
        found = await find_duplicates(
            ctx,
            DuplicateCheck(
                email=body.email, phone=body.phone, kra_pin=body.kra_pin, id_number=body.id_number
            ),
            settings,
        )
        if found.matches or found.hidden:
            names = ", ".join(m.client.display_name for m in found.matches[:3])
            detail = (
                f"Possible duplicate of {names}"
                if names
                else "This client may already be with another agent"
            )
            raise PossibleDuplicateError(detail)
    address = data.pop("address", None)
    client = Client(
        tenant_id=ctx.tenant_id,
        owner_user_id=owner,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
        address=address or {},
        display_name=display_name(body.kind, body.first_name, body.last_name, body.company_name),
    )
    _apply_identity(client, data, settings)
    if data.get("email"):
        data["email"] = str(data["email"])
    if data.get("marketing_consent"):
        client.marketing_consent_at = datetime.now(UTC)
    for field, value in data.items():
        setattr(client, field, value)
    ctx.session.add(client)
    await ctx.session.flush()
    await ctx.session.refresh(client)
    await audit.record(
        ctx,
        "client.created",
        entity_type="client",
        entity_id=client.id,
        changes={"display_name": client.display_name, "owner_user_id": owner},
    )
    return client


_AUDITED = (
    "display_name",
    "email",
    "phone",
    "kra_pin",
    "owner_user_id",
    "household_id",
    "status",
    "tags",
)


async def update_client(
    ctx: TenantContext,
    client_id: uuid.UUID,
    body: ClientUpdate,
    if_match: str | None,
    settings: Settings,
) -> Client:
    client = await get_visible_client(ctx, client_id)
    check_version(if_match, client.version)
    data = body.model_dump(exclude_unset=True)
    if "owner_user_id" in data and data["owner_user_id"] != client.owner_user_id:
        await _check_owner(ctx, data["owner_user_id"] or ctx.principal.user_id)
    await _check_links(ctx, data)
    before = {f: getattr(client, f) for f in _AUDITED}
    archived = data.pop("archived", None)
    if archived is not None:
        client.status = "archived" if archived else "active"
        client.archived_at = datetime.now(UTC) if archived else None
    if "address" in data:
        data["address"] = data["address"] or {}
    if data.get("email") is not None:
        data["email"] = str(data["email"])
    if data.get("marketing_consent") and not client.marketing_consent:
        client.marketing_consent_at = datetime.now(UTC)
    elif data.get("marketing_consent") is False:
        client.marketing_consent_at = None
    _apply_identity(client, data, settings)
    for field, value in data.items():
        setattr(client, field, value)
    client.display_name = display_name(
        client.kind, client.first_name, client.last_name, client.company_name
    )
    if not client.display_name:
        raise AppError("A client needs a name")
    client.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(client)
    await audit.record(
        ctx,
        "client.updated",
        entity_type="client",
        entity_id=client.id,
        changes=audit.diff(before, {f: getattr(client, f) for f in _AUDITED}),
    )
    return client


async def reveal_id_number(
    ctx: TenantContext, client_id: uuid.UUID, settings: Settings
) -> str | None:
    """Decrypt the ID number for someone who needs it (e.g. to fill an insurer form). Always audited."""
    client = await get_visible_client(ctx, client_id)
    if client.id_number_enc is None:
        return None
    await audit.record(ctx, "client.id_number_viewed", entity_type="client", entity_id=client.id)
    return pii_cipher(settings).decrypt(client.id_number_enc)


# ---------------------------------------------------------------- list / search


def _search(stmt: Select[Any], q: str, settings: Settings) -> Select[Any]:
    term = q.strip()
    if "@" in term:
        return stmt.where(Client.email.ilike(f"%{term}%"))
    digits = "".join(ch for ch in term if ch.isdigit())
    conditions = [Client.display_name.ilike(f"%{term}%"), Client.kra_pin == term.upper()]
    if len(digits) >= MIN_SEARCH_DIGITS:
        try:
            phone = to_e164(term)
            conditions += [Client.phone == phone, Client.alt_phone == phone]
        except InvalidPhoneError:
            conditions.append(Client.phone.like(f"%{digits}%"))
        conditions.append(Client.id_number_hash == pii_cipher(settings).lookup_hash(term))
    return stmt.where(or_(*conditions)).order_by(func.similarity(Client.display_name, term).desc())


async def list_clients(
    ctx: TenantContext,
    settings: Settings,
    *,
    q: str | None,
    tag: str | None,
    owner_user_id: str | None,
    household_id: uuid.UUID | None,
    include_archived: bool,
    cursor: uuid.UUID | None,
    limit: int,
) -> list[Client]:
    stmt = _scoped(select(Client), ctx)
    if q:
        stmt = _search(stmt, q, settings)
    stmt = stmt.order_by(Client.id.desc()).limit(limit + 1)
    if cursor is not None:
        stmt = stmt.where(Client.id < cursor)
    if tag:
        stmt = stmt.where(Client.tags.contains([tag.lower()]))
    if owner_user_id:
        stmt = stmt.where(Client.owner_user_id == owner_user_id)
    if household_id:
        stmt = stmt.where(Client.household_id == household_id)
    if not include_archived:
        stmt = stmt.where(Client.status == "active")
    return list((await ctx.session.scalars(stmt)).all())


async def count_clients(ctx: TenantContext, *, since: datetime | None = None) -> int:
    stmt = _scoped(select(func.count()).select_from(Client).where(Client.status == "active"), ctx)
    if since is not None:
        stmt = stmt.where(Client.created_at >= since)
    return int(await ctx.session.scalar(stmt) or 0)


# ---------------------------------------------------------------- contacts & activities


async def list_contacts(ctx: TenantContext, client_id: uuid.UUID) -> list[ClientContact]:
    await get_visible_client(ctx, client_id)
    stmt = (
        select(ClientContact)
        .where(ClientContact.client_id == client_id)
        .order_by(ClientContact.is_primary.desc(), ClientContact.name)
    )
    return list((await ctx.session.scalars(stmt)).all())


async def add_contact(ctx: TenantContext, client_id: uuid.UUID, body: ContactIn) -> ClientContact:
    client = await get_visible_client(ctx, client_id)
    if client.kind != "corporate":
        raise AppError("Contacts are for corporate clients")
    data = body.model_dump()
    if data["email"]:
        data["email"] = str(data["email"])
    contact = ClientContact(
        tenant_id=ctx.tenant_id, client_id=client_id, created_by=ctx.principal.user_id, **data
    )
    ctx.session.add(contact)
    await ctx.session.flush()
    await ctx.session.refresh(contact)
    return contact


async def remove_contact(ctx: TenantContext, client_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    await get_visible_client(ctx, client_id)
    contact = await ctx.session.get(ClientContact, contact_id)
    if contact is None or contact.client_id != client_id:
        raise NotFoundError("Contact not found")
    await ctx.session.delete(contact)


async def add_activity(ctx: TenantContext, client_id: uuid.UUID, body: ActivityIn) -> Activity:
    await get_visible_client(ctx, client_id)
    activity = Activity(
        tenant_id=ctx.tenant_id,
        client_id=client_id,
        kind=body.kind,
        body=body.body,
        occurred_at=body.occurred_at or datetime.now(UTC),
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(activity)
    await ctx.session.flush()
    await ctx.session.refresh(activity)
    return activity


async def list_activities(
    ctx: TenantContext, client_id: uuid.UUID, limit: int = 100
) -> list[Activity]:
    await get_visible_client(ctx, client_id)
    stmt = (
        select(Activity)
        .where(Activity.client_id == client_id)
        .order_by(Activity.occurred_at.desc())
        .limit(limit)
    )
    return list((await ctx.session.scalars(stmt)).all())


# ---------------------------------------------------------------- households


async def create_household(ctx: TenantContext, body: HouseholdIn) -> Household:
    household = Household(
        tenant_id=ctx.tenant_id,
        created_by=ctx.principal.user_id,
        updated_by=ctx.principal.user_id,
        **body.model_dump(),
    )
    ctx.session.add(household)
    try:
        async with ctx.session.begin_nested():
            await ctx.session.flush()
    except IntegrityError:  # pragma: no cover - no unique constraints besides the PK
        raise ConflictError("Household could not be created") from None
    await ctx.session.refresh(household)
    await audit.record(ctx, "household.created", entity_type="household", entity_id=household.id)
    return household


async def get_household(
    ctx: TenantContext, household_id: uuid.UUID
) -> tuple[Household, list[Client]]:
    household = await ctx.session.get(Household, household_id)
    if household is None:
        raise NotFoundError("Household not found")
    members = list(
        (
            await ctx.session.scalars(
                _scoped(select(Client).where(Client.household_id == household_id), ctx)
            )
        ).all()
    )
    return household, members


async def list_households(ctx: TenantContext) -> list[Household]:
    return list(
        (await ctx.session.scalars(select(Household).order_by(Household.name).limit(500))).all()
    )


async def update_household(
    ctx: TenantContext, household_id: uuid.UUID, body: HouseholdIn, if_match: str | None
) -> Household:
    household = await ctx.session.get(Household, household_id)
    if household is None:
        raise NotFoundError("Household not found")
    check_version(if_match, household.version)
    household.name, household.notes = body.name, body.notes
    household.updated_by = ctx.principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(household)
    return household


# ---------------------------------------------------------------- timeline


def _title(action: str) -> str:
    return {
        "client.created": "Client added",
        "client.updated": "Details changed",
        "client.id_number_viewed": "ID number viewed",
    }.get(action, action.replace(".", " ").replace("_", " ").capitalize())


async def timeline_items(
    ctx: TenantContext, client_id: uuid.UUID, extra: list[TimelineItem]
) -> list[TimelineItem]:
    """Activities and changes of the client, merged with items other modules contribute (``extra``)."""
    activities = await list_activities(ctx, client_id, limit=100)
    changes = await audit.events_for(ctx, "client", str(client_id), limit=100)
    items = [
        *extra,
        *(
            TimelineItem(
                at=a.occurred_at,
                kind="activity",
                title=a.kind.capitalize(),
                detail=a.body,
                actor=a.created_by,
                ref={"activity_id": str(a.id)},
            )
            for a in activities
        ),
        *(
            TimelineItem(at=e.occurred_at, kind="change", title=_title(e.action), actor=e.actor_id)
            for e in changes
        ),
    ]
    return sorted(items, key=lambda item: item.at, reverse=True)[:200]
