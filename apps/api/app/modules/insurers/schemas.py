"""Request/response models for insurers, products and the premium calculator. Rates are fractions sent as
strings ("0.035" = 3.5%); money is a string amount in the product's currency."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.money import AmountStr, NoFloat, RateStr
from app.core.phone import InvalidPhoneError, to_e164

Money = Annotated[Decimal, Field(ge=0)]
RatingBasis = Literal["rate_on_sum_insured", "flat", "per_member", "manual"]
Code = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-z0-9_]{1,40}$")
]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InsurerIn(_Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    short_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = (
        None
    )
    email: EmailStr | None = None
    phone: str | None = None
    mpesa_paybill: Annotated[str, StringConstraints(pattern=r"^\d{5,7}$")] | None = None
    payment_account_hint: Text | None = None
    bank_details: dict[str, str] = Field(default_factory=dict)
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return to_e164(value)
        except InvalidPhoneError as exc:
            raise ValueError(str(exc)) from None


class InsurerUpdate(InsurerIn):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
        | None
    ) = None  # type: ignore[assignment]
    is_active: bool | None = None


class InsurerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    short_name: str | None
    email: str | None
    phone: str | None
    mpesa_paybill: str | None
    payment_account_hint: str | None
    bank_details: dict[str, Any]
    notes: str | None
    is_active: bool
    version: int


class ProductBenefit(_Strict):
    code: Code
    name: Text
    basis: Literal["flat", "rate_on_sum_insured", "rate_on_premium"]
    value: Annotated[Decimal, NoFloat, Field(ge=0)] = Field(
        description="amount (flat) or fraction (rates)"
    )
    optional: bool = True
    selected_by_default: bool = False
    commissionable: bool = True


class MemberTierIn(_Strict):
    label: Text
    amount: AmountStr


class _ProductFields(_Strict):
    class_code: Code
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] = "KES"
    rating_basis: RatingBasis
    rate: RateStr | None = None
    flat_premium: AmountStr | None = None
    min_premium: AmountStr = Decimal(0)
    benefits: list[ProductBenefit] = Field(default_factory=list, max_length=30)
    member_tiers: list[MemberTierIn] = Field(default_factory=list, max_length=10)
    excess_text: Annotated[str, StringConstraints(max_length=1000)] | None = None
    commission_rate_new: RateStr | None = None
    commission_rate_renewal: RateStr | None = None
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None

    @model_validator(mode="after")
    def _basis(self) -> Self:
        if self.rating_basis == "rate_on_sum_insured" and self.rate is None:
            raise ValueError("A rate is needed for products rated on the sum insured")
        if self.rating_basis == "flat" and self.flat_premium is None:
            raise ValueError("A flat premium is needed for flat-rated products")
        if self.rating_basis == "per_member" and not self.member_tiers:
            raise ValueError(
                "Add member tiers (e.g. Principal, Spouse, Child) for per-member products"
            )
        codes = [b.code for b in self.benefits]
        if len(codes) != len(set(codes)):
            raise ValueError("Benefit codes must be unique")
        return self


class ProductIn(_ProductFields):
    insurer_id: uuid.UUID


class ProductUpdate(_ProductFields):
    is_active: bool = True


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    insurer_id: uuid.UUID
    class_code: str
    name: str
    currency: str
    rating_basis: str
    rate: RateStr | None
    flat_premium: AmountStr | None
    min_premium: AmountStr
    benefits: list[ProductBenefit]
    member_tiers: list[MemberTierIn]
    excess_text: str | None
    commission_rate_new: RateStr | None = Field(
        description="Hidden (null) for roles without commission access"
    )
    commission_rate_renewal: RateStr | None
    notes: str | None
    is_active: bool
    version: int


class InsuranceClassOut(BaseModel):
    code: str
    name: str
    business_line: str
    rating_hint: str


class PackOut(BaseModel):
    code: str
    version: str
    title: str
    signed: bool
    sign_off_note: str
    classes: list[InsuranceClassOut]


# ---- calculator


class MemberCount(_Strict):
    label: Text
    count: Annotated[int, Field(ge=1, le=500)]
    amount: AmountStr | None = Field(
        default=None, description="defaults to the product's tier amount"
    )


class AdjustmentIn(_Strict):
    name: Text
    kind: Literal["loading", "discount"]
    basis: Literal["percent", "flat"]
    value: Annotated[Decimal, NoFloat, Field(ge=0)]


class FeeIn(_Strict):
    name: Text
    amount: AmountStr


class RiskIn(_Strict):
    """What is being insured; shared by single calculations and comparisons."""

    on: date | None = Field(
        default=None, description="cover start; defaults to today in the agency's timezone"
    )
    document_kind: Literal["policy", "cover_note"] = "policy"
    sum_insured: AmountStr | None = None
    members: list[MemberCount] = Field(default_factory=list, max_length=10)
    manual_amount: AmountStr | None = None
    benefit_codes: list[Code] | None = Field(
        default=None, description="optional benefits to include; default = product defaults"
    )
    adjustments: list[AdjustmentIn] = Field(default_factory=list, max_length=10)
    fees: list[FeeIn] = Field(default_factory=list, max_length=5)
    stamp_duty_manual: AmountStr | None = None
    renewal: bool = False


class CalculateIn(RiskIn):
    product_id: uuid.UUID
    rate: RateStr | None = Field(
        default=None, description="override the product rate (e.g. insurer's special quote)"
    )


class CompareIn(RiskIn):
    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=8)


class LineOut(BaseModel):
    code: str
    label: str
    kind: str
    amount: AmountStr
    charged_to: str
    rule_id: str | None
    source: str | None
    note: str | None


class CommissionOut(BaseModel):
    base: AmountStr
    rate: RateStr
    gross: AmountStr
    wht_rate: RateStr
    wht: AmountStr
    vat: AmountStr
    net: AmountStr


class ProductRef(BaseModel):
    id: uuid.UUID
    name: str
    insurer_id: uuid.UUID
    insurer_name: str
    class_code: str
    excess_text: str | None


class CalculationOut(BaseModel):
    product: ProductRef
    currency: str
    lines: list[LineOut]
    basic_premium: AmountStr
    adjusted_premium: AmountStr
    client_total: AmountStr
    insurer_borne: AmountStr
    commission: CommissionOut | None = Field(description="Only for roles that may see commission")
    pack: dict[str, Any]
    notes: list[str]
    needs_input: list[str]


class Comparison(BaseModel):
    results: list[CalculationOut] = Field(description="Cheapest first")
    errors: list[dict[str, str]] = Field(
        default_factory=list, description="Products that could not be priced"
    )
