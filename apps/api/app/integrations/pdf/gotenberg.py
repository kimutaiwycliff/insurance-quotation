"""Gotenberg (Chromium) renderer. Internal network only; hardened flags in compose.yaml (SPEC_REVIEW §4.5).

Templates are self-contained (fonts and images as data: URIs) and carry a CSP that forbids every fetch, so the
renderer never needs network access. Gotenberg additionally denies private IPs and runs with JavaScript off.
"""

import httpx

from app.integrations.pdf import PdfRenderError

_FORM = {
    "printBackground": "true",
    "preferCssPageSize": "true",
    "marginTop": "0",
    "marginBottom": "0.45",
    "marginLeft": "0",
    "marginRight": "0",
    "emulatedMediaType": "print",
    "failOnConsoleExceptions": "false",
}


class GotenbergRenderer:
    def __init__(self, base_url: str, http: httpx.AsyncClient, *, timeout: float) -> None:
        self._url = f"{base_url.rstrip('/')}/forms/chromium/convert/html"
        self._http = http
        self._timeout = timeout

    async def render(self, html: str, *, footer_html: str | None = None) -> bytes:
        multipart = [("files", ("index.html", html.encode(), "text/html"))]
        if footer_html is not None:
            multipart.append(("files", ("footer.html", footer_html.encode(), "text/html")))
        response: httpx.Response | None = None
        for _attempt in range(2):  # Chromium occasionally fails a render under load; retry once
            try:
                response = await self._http.post(
                    self._url, data=_FORM, files=multipart, timeout=self._timeout
                )
            except httpx.HTTPError as exc:
                raise PdfRenderError(f"Gotenberg unreachable ({type(exc).__name__})") from exc
            if response.status_code < httpx.codes.INTERNAL_SERVER_ERROR:
                break
        assert response is not None  # noqa: S101 - the loop runs at least once
        if response.status_code != httpx.codes.OK:
            raise PdfRenderError(
                f"Gotenberg returned {response.status_code}: {response.text[:200]}"
            )
        return response.content
