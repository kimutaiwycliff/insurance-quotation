"""Outbound email behind a Protocol: SMTP (Mailpit locally, SES SMTP in production) and an in-memory fake."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OutboundEmail:
    to: str
    subject: str
    text: str
    html: str | None
    from_name: str
    from_address: str
    reply_to: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class EmailSender(Protocol):
    async def send(self, message: OutboundEmail) -> str:
        """Send and return the provider's message id."""
        ...


class EmailSendError(RuntimeError):
    pass
