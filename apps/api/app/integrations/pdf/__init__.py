"""HTML → PDF renderers behind a Protocol (Gotenberg in every real environment, a fake for unit tests)."""

from typing import Protocol


class PdfRenderer(Protocol):
    async def render(self, html: str, *, footer_html: str | None = None) -> bytes:
        """Render a self-contained HTML document (no external resources) to PDF bytes."""
        ...


class PdfRenderError(RuntimeError):
    pass
