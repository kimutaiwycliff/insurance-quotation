"""Request/response models for the item catalogue."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.money import AmountStr

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TaxCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None
    unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    unit_price: AmountStr = Field(ge=0)
    currency: Annotated[str, StringConstraints(min_length=3, max_length=3)] | None = Field(
        default=None, description="Defaults to the agency's currency"
    )
    tax_code: TaxCode = Field(description="A tax code of the jurisdiction pack, e.g. vat_standard")


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None
    unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    unit_price: AmountStr | None = Field(default=None, ge=0)
    tax_code: TaxCode | None = None
    active: bool | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    unit: str | None
    unit_price: AmountStr
    currency: str
    tax_code: str
    active: bool
    version: int
    created_at: datetime
