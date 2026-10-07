"""Permission registry and default roles (ADR-0007).

Better Auth stores who belongs to which organization and the membership's **role key**; the API owns what each
role may do. Every tenant endpoint declares exactly one permission via ``require_permission``; a test checks
that no route under ``/api/v1`` is left undeclared.

Record-level scoping ("own" vs "all") is applied in service queries, not here.
"""

from enum import StrEnum


class Perm(StrEnum):
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    BRANCH_READ = "branch:read"
    BRANCH_MANAGE = "branch:manage"
    MEMBER_READ = "member:read"
    NUMBERING_READ = "numbering:read"
    NUMBERING_MANAGE = "numbering:manage"
    AUDIT_READ = "audit:read"
    DOCUMENT_READ = "document:read"
    DOCUMENT_WRITE = "document:write"
    BRANDING_MANAGE = "branding:manage"
    LINK_MANAGE = "link:manage"  # create/revoke public document links
    MESSAGE_READ = "message:read"  # outbound message log
    MESSAGE_TEMPLATE_MANAGE = "message_template:manage"


class Role(StrEnum):
    """Default roles for an insurance agency (agent-first, Plan Amendment A1)."""

    OWNER = "owner"  # principal agent / agency owner: everything, incl. subscription and ownership
    ADMIN = "admin"  # office manager: everything except subscription and ownership transfer
    AGENT = "agent"  # sells and services own clients, sees own commission
    ACCOUNTS = "accounts"  # premiums, commission statements, financial reports
    ASSISTANT = "assistant"  # customer service: clients, documents, tasks; no money or commission
    VIEWER = "viewer"  # read-only


_ALL = frozenset(Perm)
_READ_BASICS = frozenset({Perm.ORG_READ, Perm.BRANCH_READ, Perm.MEMBER_READ, Perm.DOCUMENT_READ})
# Day-to-day client work: files, sending links, seeing what was sent.
_CLIENT_WORK = frozenset({Perm.DOCUMENT_WRITE, Perm.LINK_MANAGE, Perm.MESSAGE_READ})

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OWNER: _ALL,
    Role.ADMIN: _ALL,
    Role.AGENT: _READ_BASICS | _CLIENT_WORK | {Perm.NUMBERING_READ},
    Role.ACCOUNTS: _READ_BASICS
    | _CLIENT_WORK
    | {Perm.NUMBERING_READ, Perm.NUMBERING_MANAGE, Perm.AUDIT_READ},
    Role.ASSISTANT: _READ_BASICS | _CLIENT_WORK,
    Role.VIEWER: frozenset({Perm.ORG_READ, Perm.BRANCH_READ, Perm.DOCUMENT_READ}),
}

ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.OWNER: "Agency owner: full access, including subscription and ownership transfer",
    Role.ADMIN: "Office manager: full access except subscription and ownership transfer",
    Role.AGENT: "Sells and services their own clients and sees their own commission",
    Role.ACCOUNTS: "Premiums, commission statements and financial reports",
    Role.ASSISTANT: "Customer service: clients, documents and tasks; no money or commission",
    Role.VIEWER: "Read-only access",
}


def permissions_for(role: str) -> frozenset[Perm]:
    """Permissions of a role key. Unknown keys (e.g. a role removed from the code) grant nothing."""
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return frozenset()


# Highest privilege first: used when the auth service reports several roles ("admin,agent").
_ROLE_PRECEDENCE = (Role.OWNER, Role.ADMIN, Role.ACCOUNTS, Role.AGENT, Role.ASSISTANT, Role.VIEWER)


def normalise_role(raw: str | None) -> str:
    """Map an auth-service role string to one role key; unknown roles become ``viewer``."""
    keys = {part.strip().lower() for part in (raw or "").split(",")}
    for role in _ROLE_PRECEDENCE:
        if role.value in keys:
            return role.value
    # Better Auth's built-in default for invited members.
    return Role.AGENT.value if "member" in keys else Role.VIEWER.value
