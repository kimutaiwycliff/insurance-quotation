"""Item catalogue: products and services a tenant sells, reused on invoice lines."""

from decimal import Decimal

from sqlalchemy import CHAR, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Audited, Base, MoneyColumn, TenantScoped, Versioned


class Item(TenantScoped, Audited, Versioned, Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("uq_items_name", "tenant_id", "name", unique=True),
    )

    name: Mapped[str]
    description: Mapped[str | None]
    unit: Mapped[str | None]  # e.g. hour, piece, month
    unit_price: Mapped[Decimal] = mapped_column(MoneyColumn)
    currency: Mapped[str] = mapped_column(CHAR(3))
    tax_code: Mapped[str]  # a jurisdiction pack tax code
    active: Mapped[bool] = mapped_column(server_default=text("true"))
