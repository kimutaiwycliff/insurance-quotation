"""The tenant's subscription to the product, and its payments to us (platform billing)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, MoneyColumn, TenantScoped


class Subscription(TenantScoped, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        CheckConstraint("plan IN ('free', 'agent', 'agency', 'business')", name="plan"),
    )

    plan: Mapped[str]  # the plan paid for (or "free"); a running trial grants the trial plan
    billing_cycle: Mapped[str] = mapped_column(server_default="monthly")  # monthly | yearly
    extra_seats: Mapped[int] = mapped_column(server_default=text("0"))
    trial_ends_at: Mapped[datetime | None]
    current_period_end: Mapped[date | None]  # paid until (inclusive); None for free
    founding_member: Mapped[bool] = mapped_column(server_default=text("false"))
    discount_percent: Mapped[int] = mapped_column(server_default=text("0"))
    discount_until: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SubscriptionPayment(TenantScoped, Base):
    """A payment to us by M-Pesa for a plan period (our receipt to the tenant)."""

    __tablename__ = "subscription_payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        Index("uq_subscription_payments_checkout", "checkout_request_id", unique=True),
        Index("uq_subscription_payments_receipt", "receipt", unique=True),
    )

    plan: Mapped[str]
    billing_cycle: Mapped[str]
    extra_seats: Mapped[int] = mapped_column(server_default=text("0"))
    list_price: Mapped[Decimal] = mapped_column(MoneyColumn)
    discount_percent: Mapped[int] = mapped_column(server_default=text("0"))
    amount: Mapped[Decimal] = mapped_column(MoneyColumn)  # whole shillings charged
    phone: Mapped[str]
    status: Mapped[str] = mapped_column(
        server_default="pending"
    )  # pending|paid|cancelled|failed|expired
    checkout_request_id: Mapped[str | None]
    receipt: Mapped[str | None]
    result_desc: Mapped[str | None]
    period_start: Mapped[date | None]
    period_end: Mapped[date | None]
    requested_by: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
