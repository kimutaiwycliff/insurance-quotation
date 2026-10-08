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
    # Record-level scoping: ":own" sees records the member owns or is assigned; ":all" sees the agency's.
    CLIENT_READ_ALL = "client:read:all"
    CLIENT_READ_OWN = "client:read:own"
    CLIENT_WRITE = "client:write"
    LEAD_READ_ALL = "lead:read:all"
    LEAD_READ_OWN = "lead:read:own"
    LEAD_WRITE = "lead:write"
    TASK_READ_ALL = "task:read:all"
    TASK_WRITE = "task:write"
    INSURER_READ = "insurer:read"  # insurers, products, premium calculator
    INSURER_MANAGE = "insurer:manage"
    COMMISSION_READ_OWN = "commission:read:own"
    COMMISSION_READ_ALL = "commission:read:all"
    COMMISSION_MANAGE = (
        "commission:manage"  # record commission received from insurers, set expectations
    )
    PREMIUM_WRITE = "premium:write"  # record, void and remit premium payments on policies
    INVOICE_WRITE = "invoice:write"  # create and edit draft invoices and credit notes
    INVOICE_ISSUE = "invoice:issue"  # issue, void, credit and send invoices
    PAYMENT_WRITE = "payment:write"  # record, allocate and void payments received
    CATALOG_MANAGE = "catalog:manage"  # items and prices


class Role(StrEnum):
    """Default roles for an insurance agency (agent-first, Plan Amendment A1)."""

    OWNER = "owner"  # principal agent / agency owner: everything, incl. subscription and ownership
    ADMIN = "admin"  # office manager: everything except subscription and ownership transfer
    AGENT = "agent"  # sells and services own clients, sees own commission
    ACCOUNTS = "accounts"  # premiums, commission statements, financial reports
    ASSISTANT = "assistant"  # customer service: clients, documents, tasks; no money or commission
    VIEWER = "viewer"  # read-only


_ALL = frozenset(Perm)
_READ_BASICS = frozenset(
    {Perm.ORG_READ, Perm.BRANCH_READ, Perm.MEMBER_READ, Perm.DOCUMENT_READ, Perm.INSURER_READ}
)
# Day-to-day client work: files, sending links, seeing what was sent, own tasks.
_CLIENT_WORK = frozenset(
    {Perm.DOCUMENT_WRITE, Perm.LINK_MANAGE, Perm.MESSAGE_READ, Perm.TASK_WRITE}
)
_OWN_BOOK = frozenset(
    {Perm.CLIENT_READ_OWN, Perm.CLIENT_WRITE, Perm.LEAD_READ_OWN, Perm.LEAD_WRITE}
)
_AGENCY_BOOK = frozenset(
    {
        Perm.CLIENT_READ_ALL,
        Perm.CLIENT_WRITE,
        Perm.LEAD_READ_ALL,
        Perm.LEAD_WRITE,
        Perm.TASK_READ_ALL,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OWNER: _ALL,
    Role.ADMIN: _ALL,
    Role.AGENT: _READ_BASICS
    | _CLIENT_WORK
    | _OWN_BOOK
    | {
        Perm.NUMBERING_READ,
        Perm.COMMISSION_READ_OWN,
        Perm.PREMIUM_WRITE,
        Perm.INVOICE_WRITE,
        Perm.INVOICE_ISSUE,
        Perm.PAYMENT_WRITE,
    },
    Role.ACCOUNTS: _READ_BASICS
    | _CLIENT_WORK
    | {
        Perm.NUMBERING_READ,
        Perm.NUMBERING_MANAGE,
        Perm.AUDIT_READ,
        Perm.CLIENT_READ_ALL,
        Perm.INSURER_MANAGE,
        Perm.COMMISSION_READ_ALL,
        Perm.COMMISSION_MANAGE,
        Perm.PREMIUM_WRITE,
        Perm.INVOICE_WRITE,
        Perm.INVOICE_ISSUE,
        Perm.PAYMENT_WRITE,
        Perm.CATALOG_MANAGE,
    },
    Role.ASSISTANT: _READ_BASICS | _CLIENT_WORK | _AGENCY_BOOK | {Perm.INVOICE_WRITE},
    Role.VIEWER: frozenset(
        {
            Perm.ORG_READ,
            Perm.BRANCH_READ,
            Perm.DOCUMENT_READ,
            Perm.CLIENT_READ_ALL,
            Perm.LEAD_READ_ALL,
            Perm.TASK_READ_ALL,
            Perm.INSURER_READ,
        }
    ),
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
