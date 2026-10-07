"""Request/response models for documents."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Category = Literal[
    "kyc_id",
    "kyc_pin",
    "kyc_other",
    "policy_schedule",
    "certificate",
    "vehicle_logbook",
    "claim",
    "generated",
    "branding",
    "other",
]
EntityType = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]{1,39}$")]
Filename = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityRef(_Strict):
    entity_type: EntityType
    entity_id: uuid.UUID


class UploadRequest(_Strict):
    filename: Filename
    size_bytes: Annotated[int, Field(gt=0)]


class DocumentCreate(UploadRequest):
    category: Category
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    expires_on: date | None = None
    links: list[EntityRef] = Field(default_factory=list, max_length=20)


class DocumentUpdate(_Strict):
    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    category: Category | None = None
    expires_on: date | None = None
    archived: bool | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_no: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str | None
    status: str
    created_at: datetime
    finalized_at: datetime | None


class DocumentLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    title: str
    status: str
    current_version_no: int | None
    expires_on: date | None
    created_at: datetime
    version: int


class DocumentDetail(DocumentOut):
    versions: list[VersionOut]
    links: list[DocumentLinkOut]


class UploadTicket(BaseModel):
    method: Literal["PUT"] = "PUT"
    url: str
    headers: dict[str, str] = Field(description="Send exactly these headers with the PUT")
    expires_at: datetime


class UploadStarted(BaseModel):
    document: DocumentOut
    version_no: int
    upload: UploadTicket


class DownloadUrl(BaseModel):
    url: str
    expires_at: datetime
