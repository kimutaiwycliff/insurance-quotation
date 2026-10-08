"""Request/response models for book imports."""

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.money import AmountStr


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    csv: Annotated[str, StringConstraints(max_length=2_000_000)] | None = Field(
        default=None, description="The spreadsheet saved as CSV (UTF-8)"
    )
    xlsx_base64: Annotated[str, StringConstraints(max_length=2_800_000)] | None = Field(
        default=None, description="Or an Excel .xlsx file, base64-encoded (first sheet; up to 2 MB)"
    )
    mapping: dict[str, str] | None = Field(
        default=None, description="Field → column heading; detected from the headings if omitted"
    )
    assume_paid: bool = Field(
        default=True,
        description="Record the premium as paid to the insurer when there is no 'paid' column",
    )
    skip_errors: bool = Field(default=False, description="Import the good rows, skip the rest")

    @model_validator(mode="after")
    def _one_file(self) -> ImportRequest:
        if (self.csv is None) == (self.xlsx_base64 is None):
            raise ValueError("Send the file either as csv or as xlsx_base64")
        return self


class FieldInfo(BaseModel):
    key: str
    label: str
    required: bool


class RowResult(BaseModel):
    line: int = Field(description="Line in the file (the heading is line 1)")
    status: Literal["ok", "error", "skip"]
    messages: list[str]
    client_name: str
    client_action: Literal["create", "match"] | None
    insurer: str
    class_code: str | None
    policy_number: str | None
    description: str
    start_date: date | None
    end_date: date | None
    premium: AmountStr | None
    paid: AmountStr | None


class ImportPreview(BaseModel):
    columns: list[str]
    mapping: dict[str, str]
    fields: list[FieldInfo]
    problems: list[str] = Field(description="Mapping problems; nothing can be imported until fixed")
    rows: list[RowResult]
    ok: int
    errors: int
    skipped: int
    new_clients: int
    matched_clients: int


class ImportResult(BaseModel):
    import_id: uuid.UUID
    clients_created: int
    clients_matched: int
    policies_created: int
    rows_skipped: int
