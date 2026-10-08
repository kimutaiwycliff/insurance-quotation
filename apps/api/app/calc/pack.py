"""Jurisdiction pack model (ADR-0013): statutory levies, stamp duty, tax codes, WHT and classes as *data*.

Packs are YAML files under ``app/jurisdictions/packs/<code>/<version>.yaml``, validated into these types.
Every rule carries an id, a legal source and the pack version, and every amount the engine produces cites them.
A pack whose ``sign_off.status`` is not ``signed`` is usable but flagged everywhere (D4).
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BusinessLine = Literal["general", "long_term"]
DocumentKind = Literal["policy", "cover_note", "endorsement"]
IntermediaryType = Literal["agent", "broker", "non_resident", "business"]
Rounding = Literal["ROUND_HALF_UP", "ROUND_HALF_EVEN", "ROUND_DOWN"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SignOff(_Frozen):
    status: Literal["pending", "signed"]
    by: str | None = None
    signed_on: date | None = None
    note: str = ""


class Applicability(_Frozen):
    """Which risks a rule applies to. Empty lists mean "no restriction"."""

    business_lines: list[BusinessLine] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    exclude_classes: list[str] = Field(default_factory=list)
    exclude_document_kinds: list[DocumentKind] = Field(default_factory=list)

    def matches(self, *, business_line: str, class_code: str, document_kind: str) -> bool:
        if self.business_lines and business_line not in self.business_lines:
            return False
        if self.classes and class_code not in self.classes:
            return False
        if class_code in self.exclude_classes:
            return False
        return document_kind not in self.exclude_document_kinds


class _Rule(_Frozen):
    id: str
    name: str
    applies_to: Applicability = Field(default_factory=Applicability)
    effective_from: date
    effective_to: date | None = None
    source: str

    def in_force(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on < self.effective_to)


class LevyRule(_Rule):
    """A percentage levy on premium (or sum insured)."""

    basis: Literal["premium", "sum_insured"] = "premium"
    rate: Decimal = Field(ge=0, le=1)
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    # Only client-charged levies appear on quotes and debit notes; insurer-borne ones are informational.
    charged_to: Literal["client", "insurer"]
    refundable: bool = True
    commissionable: bool = False


class StampDutyRule(_Rule):
    kind: Literal["flat", "per_unit_of_sum_insured", "manual"]
    amount: Decimal | None = Field(
        default=None, ge=0, description="flat amount, or amount per unit"
    )
    unit: Decimal | None = Field(default=None, gt=0, description="e.g. 10000 for 'per KES 10,000'")
    # "per KES 10,000 or part thereof" → ceil; "pro rata" → exact fraction.
    part_units: Literal["ceil", "prorate"] = "ceil"
    note: str = ""

    @model_validator(mode="after")
    def _shape(self) -> StampDutyRule:
        if self.kind == "flat" and self.amount is None:
            raise ValueError(f"{self.id}: flat stamp duty needs an amount")
        if self.kind == "per_unit_of_sum_insured" and (self.amount is None or self.unit is None):
            raise ValueError(f"{self.id}: per-unit stamp duty needs amount and unit")
        return self


class TaxCode(_Frozen):
    code: str
    name: str
    rate: Decimal = Field(ge=0, le=1)
    kind: Literal["vat", "excise", "exempt", "zero_rated"]
    source: str
    pending_confirmation: bool = False


class InsuranceClass(_Frozen):
    code: str
    name: str
    business_line: BusinessLine
    rating_hint: Literal["rate_on_sum_insured", "flat", "per_member", "manual"] = (
        "rate_on_sum_insured"
    )


class Pack(_Frozen):
    code: str
    version: str
    title: str
    currency: str
    rounding: Rounding = "ROUND_HALF_UP"
    day_count: Literal["actual/365", "actual/actual"] = "actual/365"
    sign_off: SignOff
    premium_tax_code: str
    commission_tax_code: str
    fee_tax_code: str
    wht_on_commission: dict[IntermediaryType, Decimal]
    tax_codes: list[TaxCode]
    levies: list[LevyRule] = Field(default_factory=list)
    stamp_duty: list[StampDutyRule] = Field(default_factory=list)
    classes: list[InsuranceClass] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Pack:
        codes = {t.code for t in self.tax_codes}
        for ref in (self.premium_tax_code, self.commission_tax_code, self.fee_tax_code):
            if ref not in codes:
                raise ValueError(f"Unknown tax code {ref!r}")
        ids = [r.id for r in [*self.levies, *self.stamp_duty]]
        if len(ids) != len(set(ids)):
            raise ValueError("Rule ids must be unique")
        class_codes = [c.code for c in self.classes]
        if len(class_codes) != len(set(class_codes)):
            raise ValueError("Class codes must be unique")
        return self

    @property
    def signed(self) -> bool:
        return self.sign_off.status == "signed"

    def tax(self, code: str) -> TaxCode:
        return next(t for t in self.tax_codes if t.code == code)

    def insurance_class(self, code: str) -> InsuranceClass | None:
        return next((c for c in self.classes if c.code == code), None)
