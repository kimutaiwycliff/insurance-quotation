"""Plans, prices and what each includes (docs/PRICING.md, approved 2026-10-08).

Prices are KES, VAT-inclusive. Changing a price here affects new payments only; a paid period keeps what was
paid for. Features are checked by the API (``require_feature``); limits by the services that own the data.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class Feature(StrEnum):
    INSURANCE = "insurance"  # insurers, insurance quotes, policies, renewals
    COMPARISON_QUOTES = "comparison_quotes"  # several insurers on one quote
    COMMISSION = "commission"
    BOOK_IMPORT = "book_import"
    CLIENT_REMINDERS = "client_reminders"  # renewal and invoice emails to clients
    BRANDING = "branding"  # own logo and colours (Free shows "Made with ...")
    ETIMS = "etims"
    TEAM = "team"  # roles and own-client scoping for several members


class Limit(StrEnum):
    CLIENTS = "clients"
    DOCUMENTS_PER_MONTH = "documents_per_month"  # invoices, credit notes and sales quotes issued
    SEATS = "seats"


@dataclass(frozen=True, slots=True)
class Plan:
    code: str
    name: str
    tagline: str
    monthly: Decimal
    yearly: Decimal
    included_seats: int
    extra_seat_monthly: Decimal | None
    features: frozenset[Feature]
    limits: dict[Limit, int] = field(
        default_factory=dict
    )  # absent = unlimited (seats: see included_seats)
    public: bool = True


_PAID_COMMON = frozenset({Feature.CLIENT_REMINDERS, Feature.BRANDING, Feature.ETIMS})
_AGENT = _PAID_COMMON | {
    Feature.INSURANCE,
    Feature.COMPARISON_QUOTES,
    Feature.COMMISSION,
    Feature.BOOK_IMPORT,
}

PLANS: dict[str, Plan] = {
    p.code: p
    for p in (
        Plan(
            code="free",
            name="Free",
            tagline="For agents starting out",
            monthly=Decimal(0),
            yearly=Decimal(0),
            included_seats=1,
            extra_seat_monthly=None,
            features=frozenset({Feature.INSURANCE}),
            limits={Limit.CLIENTS: 50, Limit.DOCUMENTS_PER_MONTH: 10},
        ),
        Plan(
            code="agent",
            name="Agent",
            tagline="Everything for one working agent",
            monthly=Decimal(1500),
            yearly=Decimal(15000),
            included_seats=1,
            extra_seat_monthly=None,
            features=frozenset(_AGENT),
        ),
        Plan(
            code="agency",
            name="Agency",
            tagline="For agencies with a team",
            monthly=Decimal(4500),
            yearly=Decimal(45000),
            included_seats=5,
            extra_seat_monthly=Decimal(700),
            features=frozenset(_AGENT | {Feature.TEAM}),
        ),
        Plan(
            code="business",
            name="Business",
            tagline="Quotes, invoices and M-Pesa for small businesses",
            monthly=Decimal(999),
            yearly=Decimal(9990),
            included_seats=3,
            extra_seat_monthly=None,
            features=frozenset(_PAID_COMMON | {Feature.TEAM}),
        ),
    )
}

TRIAL_PLAN = "agency"  # 30 days of everything, team included
TRIAL_DAYS = 30
GRACE_DAYS = 7  # after a paid period ends, before the account turns read-only
FOUNDING_MEMBERS = 100  # the first paying tenants get the founding discount
FOUNDING_DISCOUNT_PERCENT = 50
FOUNDING_MONTHS = 12


def price(plan: Plan, cycle: str, extra_seats: int) -> Decimal:
    """Undiscounted price for one period."""
    base = plan.yearly if cycle == "yearly" else plan.monthly
    if extra_seats and plan.extra_seat_monthly is not None:
        seats_monthly = plan.extra_seat_monthly * extra_seats
        base += seats_monthly * (
            10 if cycle == "yearly" else 1
        )  # yearly: 2 months free on seats too
    return base
