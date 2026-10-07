"""In-memory sender for tests."""

import uuid

from app.integrations.email import OutboundEmail


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[OutboundEmail] = []

    async def send(self, message: OutboundEmail) -> str:
        self.sent.append(message)
        return f"<{uuid.uuid4()}@fake>"
