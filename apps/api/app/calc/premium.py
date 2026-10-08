"""Premium engine v1 (pure): basic premium → benefits → loadings/discounts → levies → stamp duty → fees,
plus the agent's commission. Spec §6.2-6.3 as corrected by SPEC_REVIEW §2.2.

Every line of the result names the rule that produced it (pack rule id, version and legal source), so any
amount on a quote can be explained and reproduced. Only client-charged lines make up the client total;
insurer-borne levies are reported separately and never billed.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.calc.commission import Commission
from app.calc.commission import commission as compute_commission
from app.calc.pack import IntermediaryType, Pack
from app.core.money import Money

ZERO = Decimal(0)
LineKind = Literal[
    "premium", "benefit", "loading", "discount", "levy", "stamp_duty", "fee", "fee_tax"
]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MemberTier(_In):
    label: str
    count: int = Field(ge=1)
    amount: Decimal = Field(ge=0, description="premium per member")


class Rating(_In):
    basis: Literal["rate_on_sum_insured", "flat", "per_member", "manual"]
    sum_insured: Decimal | None = Field(default=None, ge=0)
    rate: Decimal | None = Field(default=None, ge=0, le=1, description="fraction, e.g. 0.04 = 4%")
    flat_amount: Decimal | None = Field(default=None, ge=0)
    members: list[MemberTier] = Field(default_factory=list)
    manual_amount: Decimal | None = Field(default=None, ge=0)


class Benefit(_In):
    code: str
    name: str
    basis: Literal["flat", "rate_on_sum_insured", "rate_on_premium"]
    value: Decimal = Field(ge=0, description="amount for flat; fraction for rates")
    sum_insured: Decimal | None = Field(
        default=None, ge=0, description="defaults to the risk's sum insured"
    )
    commissionable: bool = True


class Adjustment(_In):
    name: str
    kind: Literal["loading", "discount"]
    basis: Literal["percent", "flat"]
    value: Decimal = Field(ge=0, description="fraction for percent (0.1 = 10%), amount for flat")


class Fee(_In):
    name: str
    amount: Decimal = Field(ge=0)


class PremiumRequest(_In):
    class_code: str
    currency: str
    on: date = Field(description="cover start date: selects the rules in force")
    document_kind: Literal["policy", "cover_note", "endorsement"] = "policy"
    rating: Rating
    min_premium: Decimal = Field(default=ZERO, ge=0)
    benefits: list[Benefit] = Field(default_factory=list)
    adjustments: list[Adjustment] = Field(default_factory=list)
    fees: list[Fee] = Field(default_factory=list)
    stamp_duty_manual: Decimal | None = Field(default=None, ge=0)
    commission_rate: Decimal | None = Field(default=None, ge=0, le=1)
    intermediary_type: IntermediaryType = "agent"


class Line(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    label: str
    kind: LineKind
    amount: Decimal
    charged_to: Literal["client", "insurer"] = "client"
    commissionable: bool = False
    rule_id: str | None = None
    source: str | None = None
    note: str | None = None


class PackRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    version: str
    signed: bool


class PremiumResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    currency: str
    lines: list[Line]
    basic_premium: Decimal
    adjusted_premium: Decimal
    client_total: Decimal
    insurer_borne: Decimal
    commission: Commission | None
    pack: PackRef
    notes: list[str]
    needs_input: list[str] = Field(description="inputs still missing before the total is final")


class PremiumInputError(ValueError):
    pass


@dataclass
class _Ctx:
    pack: Pack
    request: PremiumRequest
    lines: list[Line] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)

    def round(self, amount: Decimal) -> Decimal:
        return Money(amount, self.request.currency).rounded(self.pack.rounding).amount


def _basic(ctx: _Ctx) -> Decimal:
    r = ctx.request.rating
    match r.basis:
        case "rate_on_sum_insured":
            if r.sum_insured is None or r.rate is None:
                raise PremiumInputError("Rate on sum insured needs a sum insured and a rate")
            return ctx.round(r.sum_insured * r.rate)
        case "flat":
            if r.flat_amount is None:
                raise PremiumInputError("Flat rating needs an amount")
            return ctx.round(r.flat_amount)
        case "per_member":
            if not r.members:
                raise PremiumInputError("Per-member rating needs at least one member tier")
            return sum((ctx.round(m.amount * m.count) for m in r.members), ZERO)
        case "manual":
            if r.manual_amount is None:
                raise PremiumInputError("Manual rating needs the premium amount")
            return ctx.round(r.manual_amount)


def _benefit_amount(ctx: _Ctx, benefit: Benefit, basic: Decimal) -> Decimal:
    match benefit.basis:
        case "flat":
            return ctx.round(benefit.value)
        case "rate_on_premium":
            return ctx.round(basic * benefit.value)
        case "rate_on_sum_insured":
            base = (
                benefit.sum_insured
                if benefit.sum_insured is not None
                else ctx.request.rating.sum_insured
            )
            if base is None:
                raise PremiumInputError(f"Benefit {benefit.name} needs a sum insured")
            return ctx.round(base * benefit.value)


def _levies(ctx: _Ctx, premium: Decimal, business_line: str) -> None:
    req = ctx.request
    for rule in ctx.pack.levies:
        if not (
            rule.in_force(req.on)
            and rule.applies_to.matches(
                business_line=business_line,
                class_code=req.class_code,
                document_kind=req.document_kind,
            )
        ):
            continue
        base = premium if rule.basis == "premium" else (req.rating.sum_insured or ZERO)
        amount = base * rule.rate
        if rule.minimum is not None:
            amount = max(amount, rule.minimum)
        if rule.maximum is not None:
            amount = min(amount, rule.maximum)
        ctx.lines.append(
            Line(
                code=rule.id,
                label=rule.name,
                kind="levy",
                amount=ctx.round(amount),
                charged_to=rule.charged_to,
                commissionable=rule.commissionable,
                rule_id=f"{rule.id}@{ctx.pack.version}",
                source=rule.source,
            )
        )


def _stamp_duty(ctx: _Ctx, business_line: str) -> None:
    req = ctx.request
    rule = next(
        (
            r
            for r in ctx.pack.stamp_duty
            if r.in_force(req.on)
            and r.applies_to.matches(
                business_line=business_line,
                class_code=req.class_code,
                document_kind=req.document_kind,
            )
        ),
        None,
    )
    if rule is None:
        if req.document_kind == "cover_note" and ctx.pack.stamp_duty:
            ctx.notes.append("Cover notes are not stamped.")
        return
    rule_id, source = f"{rule.id}@{ctx.pack.version}", rule.source
    match rule.kind:
        case "flat":
            amount = rule.amount or ZERO
            ctx.lines.append(
                Line(
                    code=rule.id,
                    label=rule.name,
                    kind="stamp_duty",
                    amount=ctx.round(amount),
                    rule_id=rule_id,
                    source=source,
                )
            )
        case "per_unit_of_sum_insured":
            si = req.rating.sum_insured
            if si is None:
                raise PremiumInputError("Stamp duty for this class needs the sum insured")
            unit, per = rule.unit or Decimal(1), rule.amount or ZERO
            units = (
                (si / unit).to_integral_value(rounding="ROUND_CEILING")
                if rule.part_units == "ceil"
                else si / unit
            )
            ctx.lines.append(
                Line(
                    code=rule.id,
                    label=rule.name,
                    kind="stamp_duty",
                    amount=ctx.round(units * per),
                    rule_id=rule_id,
                    source=source,
                )
            )
        case "manual":
            if req.stamp_duty_manual is None:
                ctx.needs.append("stamp_duty")
                ctx.notes.append(
                    rule.note or f"Enter {rule.name.lower()} from the insurer's quote."
                )
                return
            ctx.lines.append(
                Line(
                    code=rule.id,
                    label=rule.name,
                    kind="stamp_duty",
                    amount=ctx.round(req.stamp_duty_manual),
                    note="entered manually",
                    rule_id=rule_id,
                    source=source,
                )
            )


def calculate(pack: Pack, request: PremiumRequest) -> PremiumResult:
    """Compute the premium breakdown. Raises :class:`PremiumInputError` for inconsistent inputs."""
    ctx = _Ctx(pack=pack, request=request)
    klass = pack.insurance_class(request.class_code)
    if klass is None:
        raise PremiumInputError(f"Unknown class {request.class_code!r} for pack {pack.code}")

    basic = _basic(ctx)
    min_premium = ctx.round(request.min_premium)
    if basic < min_premium:
        ctx.notes.append(f"Minimum premium applied ({request.currency} {min_premium:,}).")
        basic = min_premium
    ctx.lines.append(
        Line(
            code="basic_premium",
            label="Basic premium",
            kind="premium",
            amount=basic,
            commissionable=True,
        )
    )

    benefits_total = ZERO
    for benefit in request.benefits:
        amount = _benefit_amount(ctx, benefit, basic)
        benefits_total += amount
        ctx.lines.append(
            Line(
                code=f"benefit.{benefit.code}",
                label=benefit.name,
                kind="benefit",
                amount=amount,
                commissionable=benefit.commissionable,
            )
        )

    subtotal = basic + benefits_total
    adjusted = subtotal
    for adj in request.adjustments:
        amount = ctx.round(subtotal * adj.value) if adj.basis == "percent" else ctx.round(adj.value)
        signed = amount if adj.kind == "loading" else -amount
        adjusted += signed
        ctx.lines.append(
            Line(
                code=f"{adj.kind}.{adj.name.lower().replace(' ', '_')}",
                label=adj.name,
                kind=adj.kind,
                amount=signed,
                commissionable=True,
            )
        )
    if adjusted < min_premium:
        floor = min_premium - adjusted
        ctx.lines.append(
            Line(
                code="minimum_premium_topup",
                label="Minimum premium adjustment",
                kind="loading",
                amount=floor,
                commissionable=True,
            )
        )
        ctx.notes.append(
            "Discounts would take the premium below the minimum; topped up to the minimum."
        )
        adjusted = min_premium

    _levies(ctx, adjusted, klass.business_line)
    _stamp_duty(ctx, klass.business_line)

    fee_tax = pack.tax(pack.fee_tax_code)
    for fee in request.fees:
        amount = ctx.round(fee.amount)
        ctx.lines.append(
            Line(
                code=f"fee.{fee.name.lower().replace(' ', '_')}",
                label=fee.name,
                kind="fee",
                amount=amount,
            )
        )
        if fee_tax.rate > 0:
            ctx.lines.append(
                Line(
                    code=f"fee_tax.{fee_tax.code}",
                    label=f"{fee_tax.name} on {fee.name}",
                    kind="fee_tax",
                    amount=ctx.round(amount * fee_tax.rate),
                    source=fee_tax.source,
                    note="pending confirmation" if fee_tax.pending_confirmation else None,
                )
            )

    client_total = sum((line.amount for line in ctx.lines if line.charged_to == "client"), ZERO)
    insurer_borne = sum((line.amount for line in ctx.lines if line.charged_to == "insurer"), ZERO)

    commission = None
    if request.commission_rate is not None:
        base = sum(
            (
                line.amount
                for line in ctx.lines
                if line.commissionable and line.charged_to == "client"
            ),
            ZERO,
        )
        commission = compute_commission(
            pack,
            base,
            request.commission_rate,
            currency=request.currency,
            intermediary=request.intermediary_type,
        )

    if not pack.signed:
        ctx.notes.append(
            f"Statutory rates from the {pack.title} pack {pack.version} are pending adviser sign-off."
        )
    return PremiumResult(
        currency=request.currency,
        lines=ctx.lines,
        basic_premium=basic,
        adjusted_premium=adjusted,
        client_total=client_total,
        insurer_borne=insurer_borne,
        commission=commission,
        pack=PackRef(code=pack.code, version=pack.version, signed=pack.signed),
        notes=ctx.notes,
        needs_input=ctx.needs,
    )
