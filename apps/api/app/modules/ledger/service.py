"""Ledger postings (ADR-0012). Other modules post through ``post``; the database checks every entry balances."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.ledger.models import ACCOUNTS, JournalEntry, JournalLine

ZERO = Decimal(0)


class UnbalancedEntryError(AppError):
    code = "ledger_unbalanced"
    title = "A ledger entry must balance"


@dataclass(frozen=True, slots=True)
class Leg:
    account: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO


async def post(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    occurred_on: date,
    source_type: str,
    source_id: uuid.UUID,
    memo: str,
    currency: str,
    client_id: uuid.UUID | None,
    legs: list[Leg],
    actor: str | None,
) -> JournalEntry:
    """Record one balanced entry. Zero legs are dropped; an entry with nothing left is skipped."""
    legs = [leg for leg in legs if leg.debit or leg.credit]
    for leg in legs:
        if (
            leg.account not in ACCOUNTS
            or leg.debit < 0
            or leg.credit < 0
            or (leg.debit and leg.credit)
        ):
            raise UnbalancedEntryError(f"Invalid leg {leg}")
    if sum((leg.debit for leg in legs), ZERO) != sum((leg.credit for leg in legs), ZERO):
        raise UnbalancedEntryError(f"{memo}: debits and credits differ")
    entry = JournalEntry(
        tenant_id=tenant_id,
        occurred_on=occurred_on,
        source_type=source_type,
        source_id=source_id,
        memo=memo,
        created_by=actor,
    )
    session.add(entry)
    await session.flush()
    for leg in legs:
        session.add(
            JournalLine(
                tenant_id=tenant_id,
                entry_id=entry.id,
                account=leg.account,
                debit=leg.debit,
                credit=leg.credit,
                currency=currency,
                client_id=client_id,
            )
        )
    await session.flush()
    return entry


async def reverse(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    occurred_on: date,
    memo: str,
    actor: str | None,
) -> int:
    """Post the mirror image of every entry recorded for a source (e.g. voiding an invoice)."""
    entries = (
        await session.scalars(
            select(JournalEntry).where(
                JournalEntry.source_type == source_type, JournalEntry.source_id == source_id
            )
        )
    ).all()
    for entry in entries:
        lines = (
            await session.scalars(select(JournalLine).where(JournalLine.entry_id == entry.id))
        ).all()
        if not lines:
            continue
        await post(
            session,
            tenant_id=tenant_id,
            occurred_on=occurred_on,
            source_type=f"{source_type}_reversal",
            source_id=source_id,
            memo=memo,
            currency=lines[0].currency,
            client_id=lines[0].client_id,
            legs=[Leg(line.account, debit=line.credit, credit=line.debit) for line in lines],
            actor=actor,
        )
    return len(entries)


async def balance(
    session: AsyncSession, account: str, *, client_id: uuid.UUID | None = None, currency: str
) -> Decimal:
    """Debit-positive balance of an account (optionally for one client)."""
    stmt = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).where(
        JournalLine.account == account, JournalLine.currency == currency
    )
    if client_id is not None:
        stmt = stmt.where(JournalLine.client_id == client_id)
    return Decimal(await session.scalar(stmt) or 0)


async def trial_balance(session: AsyncSession, currency: str) -> dict[str, Decimal]:
    rows = await session.execute(
        select(JournalLine.account, func.sum(JournalLine.debit - JournalLine.credit))
        .where(JournalLine.currency == currency)
        .group_by(JournalLine.account)
    )
    return {account: Decimal(total) for account, total in rows}
