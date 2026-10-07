"""In-memory renderer for unit tests: returns a tiny PDF and remembers what it was asked to render."""

FAKE_PDF = b"%PDF-1.4\n% fake\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class FakeRenderer:
    def __init__(self) -> None:
        self.rendered: list[str] = []

    async def render(self, html: str, *, footer_html: str | None = None) -> bytes:
        self.rendered.append(html)
        return FAKE_PDF
