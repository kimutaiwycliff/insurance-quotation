"""Trial-only pricing: no free plan. Unpaid agencies are stored as plan 'trial'.

Agencies whose trial already ended while on the old Free plan get a fresh 14-day trial, so nobody is locked
out by the change. Running trials keep their end date.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_plans(old: str, new: str) -> None:
    op.execute("ALTER TABLE app.subscriptions DROP CONSTRAINT ck_subscriptions_plan")
    # Row-level security is off for the owner here because the update is the same for every tenant.
    op.execute("ALTER TABLE app.subscriptions NO FORCE ROW LEVEL SECURITY")
    op.execute(
        sa.text("UPDATE app.subscriptions SET plan = :new WHERE plan = :old").bindparams(
            new=new, old=old
        )
    )
    if new == "trial":
        op.execute(
            "UPDATE app.subscriptions SET trial_ends_at = now() + interval '14 days' "
            "WHERE plan = 'trial' AND (trial_ends_at IS NULL OR trial_ends_at < now())"
        )
    op.execute("ALTER TABLE app.subscriptions FORCE ROW LEVEL SECURITY")
    unpaid = {"trial": "'trial'", "free": "'free'"}[new]  # fixed values, never input
    op.execute(
        "ALTER TABLE app.subscriptions ADD CONSTRAINT ck_subscriptions_plan "
        f"CHECK (plan IN ({unpaid}, 'agent', 'agency', 'business'))"
    )


def upgrade() -> None:
    _replace_plans("free", "trial")


def downgrade() -> None:
    _replace_plans("trial", "free")
