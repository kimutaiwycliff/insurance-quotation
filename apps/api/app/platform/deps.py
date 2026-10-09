"""FastAPI dependencies for tenant endpoints.

A tenant request goes through, in order:

1. bearer token → verified :class:`AccessClaims` (no DB);
2. one transaction with ``app.tenant_id`` set from the token's organization (RLS applies from here on);
3. principal resolution from the membership mirror (lazy provisioning on first sight);
4. MFA policy, rate limit, then the endpoint's permission.

The transaction commits when the endpoint returns, **before** the response is sent (``scope="function"``),
so a client never sees a success that was later rolled back.
"""

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated, Any, Protocol

import structlog
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import set_tenant_context
from app.core.errors import (
    AppError,
    MfaRequiredError,
    PermissionDeniedError,
    RateLimitedError,
)
from app.core.permissions import Perm
from app.core.ratelimit import hit
from app.core.security import AccessClaims, ServiceClaims, bearer_token
from app.core.tenancy import tenant_id_for_org
from app.platform.resources import Resources, get_resources

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class NoActiveOrganizationError(AppError):
    status = PermissionDeniedError.status
    code = "no_active_organization"
    title = "Create or select an organization first"


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    email: str
    name: str
    tenant_id: uuid.UUID
    org_id: str
    membership_id: uuid.UUID
    role: str
    permissions: frozenset[Perm]
    mfa_enrolled: bool
    # The tenant's plan (R2.5). "*" grants every feature (system actors such as the M-Pesa jobs).
    plan: str = "system"
    features: frozenset[str] = frozenset({"*"})
    read_only: bool = False  # subscription lapsed: reads only, until the tenant pays again


class SubscriptionInactiveError(AppError):
    status = HTTPStatus.PAYMENT_REQUIRED
    code = "subscription_inactive"
    title = "Your subscription has lapsed: renew it in Settings → Plan & billing to make changes"


class FeatureNotInPlanError(AppError):
    status = HTTPStatus.PAYMENT_REQUIRED
    code = "plan_feature"
    title = "Your plan does not include this"


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class PrincipalResolver(Protocol):
    """Implemented by the tenancy module; wired in ``app.main``."""

    def __call__(
        self, session: AsyncSession, claims: AccessClaims, tenant_id: uuid.UUID
    ) -> Coroutine[Any, Any, Principal]: ...


def own_scope(principal: Principal, read_all: Perm) -> str | None:
    """``None`` if the member sees every record, else their user id (they see only what they own)."""
    return None if read_all in principal.permissions else principal.user_id


@dataclass(frozen=True, slots=True)
class TenantContext:
    session: AsyncSession
    principal: Principal
    request_id: str | None

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.principal.tenant_id


ResourcesDep = Annotated[Resources, Depends(get_resources)]


async def access_claims(
    resources: ResourcesDep,
    authorization: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> AccessClaims:
    return await resources.token_verifier.verify_access_token(bearer_token(authorization))


async def service_claims(
    resources: ResourcesDep,
    authorization: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> ServiceClaims:
    return await resources.token_verifier.verify_service_token(bearer_token(authorization))


async def _enforce_rate_limit(resources: Resources, request: Request, principal: Principal) -> None:
    settings = resources.settings
    if not settings.rate_limit_enabled:
        return
    is_read = request.method in _READ_METHODS
    limit = settings.rate_limit_read_per_minute if is_read else settings.rate_limit_write_per_minute
    decision = await hit(
        resources.valkey,
        f"{principal.tenant_id}:{principal.user_id}:{'r' if is_read else 'w'}",
        limit=limit,
    )
    if not decision.allowed:
        raise RateLimitedError(decision.retry_after_seconds)


async def _tenant_context(
    request: Request,
    resources: ResourcesDep,
    claims: Annotated[AccessClaims, Depends(access_claims)],
) -> AsyncIterator[TenantContext]:
    if claims.org_id is None:
        raise NoActiveOrganizationError()
    tenant_id = tenant_id_for_org(claims.org_id)
    resolver = resources.principal_resolver
    if resolver is None:  # pragma: no cover - wiring error caught by any API test
        raise RuntimeError("principal_resolver is not configured")
    async with resources.session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        principal = await resolver(session, claims, tenant_id)
        structlog.contextvars.bind_contextvars(tenant_id=str(tenant_id), user_id=principal.user_id)
        await _enforce_rate_limit(resources, request, principal)
        request_id = getattr(request.state, "request_id", None)
        yield TenantContext(session=session, principal=principal, request_id=request_id)


def require_permission(
    permission: Perm | tuple[Perm, ...] | None,
    *,
    allow_without_mfa: bool = False,
    allow_read_only: bool = False,
) -> Callable[..., Coroutine[Any, Any, TenantContext]]:
    """Dependency factory: the endpoint's tenant context, after checking MFA policy and ``permission``.

    A tuple means "any of" (e.g. ``client:read:own`` or ``client:read:all``; the service then scopes rows).
    ``permission=None`` is reserved for endpoints every member may call (``/me``).
    """
    required = permission if isinstance(permission, tuple) else (permission,) if permission else ()

    async def dependency(
        request: Request,
        ctx: Annotated[TenantContext, Depends(_tenant_context, scope="function")],
        resources: ResourcesDep,
    ) -> TenantContext:
        principal = ctx.principal
        if principal.read_only and not allow_read_only and request.method not in _SAFE_METHODS:
            raise SubscriptionInactiveError()
        if (
            not allow_without_mfa
            and principal.role in resources.settings.mfa_enforced_roles
            and not principal.mfa_enrolled
        ):
            raise MfaRequiredError()
        if required and not any(p in principal.permissions for p in required):
            raise PermissionDeniedError(f"Requires the '{' or '.join(required)}' permission")
        return ctx

    dependency.required_permission = permission  # type: ignore[attr-defined]
    return dependency


def require_feature(feature: str) -> Callable[..., Coroutine[Any, Any, None]]:
    """Router or route dependency: the tenant's plan must include ``feature`` (R2.5)."""

    async def dependency(
        ctx: Annotated[TenantContext, Depends(_tenant_context, scope="function")],
    ) -> None:
        features = ctx.principal.features
        if "*" not in features and feature not in features:
            raise FeatureNotInPlanError(
                f"Your plan does not include {feature.replace('_', ' ')}. "
                "See Settings → Plan & billing to upgrade."
            )

    return dependency
