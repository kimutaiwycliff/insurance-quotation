"""Tenant identity (ADR-0003).

A tenant is a Better Auth *organization*. Its id is derived deterministically from the organization id, so the
API can set the RLS tenant context straight from a verified token without a lookup that would have to bypass
RLS. ``tenants.auth_org_id`` keeps the original id; if the identity provider ever changes, new tenants can use a
different namespace while existing ids stay stable.
"""

import uuid

# Fixed forever: changing it would orphan every tenant.
TENANT_NAMESPACE = uuid.UUID("6f0c7a3e-1d1b-5c2a-9a51-2b7f3c9d8e10")
MAX_ORG_ID_LENGTH = 255


def tenant_id_for_org(org_id: str) -> uuid.UUID:
    if not org_id or len(org_id) > MAX_ORG_ID_LENGTH:
        raise ValueError("organization id must be 1-255 characters")
    return uuid.uuid5(TENANT_NAMESPACE, org_id)
