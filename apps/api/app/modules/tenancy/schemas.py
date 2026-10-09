"""Request/response models for tenancy endpoints."""

import uuid
import zoneinfo
from datetime import date, datetime, time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.core.money import ISO_4217_MINOR_UNITS
from app.core.permissions import Perm

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
BranchCode = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{1,10}$")
]
IntermediaryType = Literal["agent", "broker", "business"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TenantSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str | None


class MeOut(BaseModel):
    user_id: str
    email: str
    name: str
    tenant: TenantSummary
    role: str
    permissions: list[Perm]
    mfa_enrolled: bool
    mfa_required: bool = Field(description="True when the role requires 2FA but it is not enrolled")


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str | None
    status: str
    legal_name: str | None
    registration_number: str | None
    tax_pin: str | None
    intermediary_type: str
    licence_number: str | None
    licence_expiry: date | None
    email: str | None
    phone: str | None
    address: dict[str, Any]
    country_code: str
    default_currency: str
    timezone: str
    locale: str
    fiscal_year_start_month: int
    quiet_hours_start: time | None
    quiet_hours_end: time | None
    multi_insurer_quotes: bool
    renewal_reminder_days: list[int]
    renewal_client_emails: bool
    billing_reminders: bool
    etims_enabled: bool
    invoice_reminder_days_before: list[int]
    invoice_reminder_days_after: list[int]
    version: int


class OrganizationUpdate(_Strict):
    """Partial update: only the fields sent are changed."""

    name: Name | None = None
    legal_name: Name | None = None
    registration_number: ShortText | None = None
    tax_pin: (
        Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, max_length=20)]
        | None
    ) = None
    intermediary_type: IntermediaryType | None = None
    licence_number: ShortText | None = None
    licence_expiry: date | None = None
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(pattern=r"^\+?[0-9 ]{7,20}$")] | None = None
    address: dict[str, str] | None = None
    default_currency: str | None = None
    timezone: str | None = None
    locale: Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")] | None = None
    fiscal_year_start_month: Annotated[int, Field(ge=1, le=12)] | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    multi_insurer_quotes: bool | None = None
    renewal_reminder_days: (
        Annotated[list[Annotated[int, Field(ge=1, le=120)]], Field(min_length=1, max_length=6)]
        | None
    ) = Field(default=None, description="Days before expiry on which renewals are reminded")
    renewal_client_emails: bool | None = Field(
        default=None, description="Also email clients a renewal reminder (agent is always reminded)"
    )
    billing_reminders: bool | None = Field(
        default=None,
        description="Email clients before and after invoices fall due, and before quotes expire",
    )
    etims_enabled: bool | None = Field(
        default=None, description="Record the KRA eTIMS CU invoice number on issued invoices"
    )
    invoice_reminder_days_before: (
        Annotated[list[Annotated[int, Field(ge=1, le=60)]], Field(min_length=1, max_length=4)]
        | None
    ) = None
    invoice_reminder_days_after: (
        Annotated[list[Annotated[int, Field(ge=1, le=120)]], Field(min_length=1, max_length=6)]
        | None
    ) = None

    @field_validator("invoice_reminder_days_before", "invoice_reminder_days_after")
    @classmethod
    def _offsets(cls, value: list[int] | None) -> list[int] | None:
        return sorted(set(value)) if value is not None else None

    @field_validator("renewal_reminder_days")
    @classmethod
    def _days(cls, value: list[int] | None) -> list[int] | None:
        return sorted(set(value), reverse=True) if value is not None else None

    @field_validator("default_currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        if value is not None and value not in ISO_4217_MINOR_UNITS:
            raise ValueError("unsupported currency")
        return value

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in zoneinfo.available_timezones():
            raise ValueError("unknown IANA timezone")
        return value


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    auth_user_id: str
    email: str
    name: str
    role: str
    status: str
    job_title: str | None
    created_at: datetime


class RoleOut(BaseModel):
    key: str
    description: str
    permissions: list[Perm]
    mfa_required: bool


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    tax_branch_id: str | None
    email: str | None
    phone: str | None
    address: dict[str, Any]
    is_head_office: bool
    archived_at: datetime | None
    version: int


class BranchCreate(_Strict):
    name: Name
    code: BranchCode
    tax_branch_id: ShortText | None = None
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(pattern=r"^\+?[0-9 ]{7,20}$")] | None = None
    address: dict[str, str] = Field(default_factory=dict)
    is_head_office: bool = False


class BranchUpdate(_Strict):
    name: Name | None = None
    code: BranchCode | None = None
    tax_branch_id: ShortText | None = None
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(pattern=r"^\+?[0-9 ]{7,20}$")] | None = None
    address: dict[str, str] | None = None
    is_head_office: bool | None = None
    archived: bool | None = None


# ---- internal (auth service → API)


class InternalUser(_Strict):
    user_id: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    email: EmailStr
    name: Annotated[str, StringConstraints(max_length=255)] = ""


class TenantProvision(_Strict):
    org_id: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    name: Name
    slug: Annotated[str, StringConstraints(max_length=255)] | None = None
    owner: InternalUser


class MembershipUpsert(_Strict):
    org_id: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    org_name: Name
    org_slug: Annotated[str, StringConstraints(max_length=255)] | None = None
    user: InternalUser
    role: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class MembershipRemove(_Strict):
    org_id: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    user_id: Annotated[str, StringConstraints(min_length=1, max_length=255)]


class ProvisionResult(BaseModel):
    tenant_id: uuid.UUID
    created: bool
