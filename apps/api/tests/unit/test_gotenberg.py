"""Gotenberg renderer retries one transient failure (timeout or 5xx) and reports the rest."""

import httpx
import pytest
import respx

from app.integrations.pdf import PdfRenderError
from app.integrations.pdf.gotenberg import GotenbergRenderer

URL = "http://gotenberg.test/forms/chromium/convert/html"


@pytest.fixture
async def renderer() -> GotenbergRenderer:
    return GotenbergRenderer("http://gotenberg.test", httpx.AsyncClient(), timeout=1)


@respx.mock
async def test_retries_a_timeout_once(renderer: GotenbergRenderer) -> None:
    route = respx.post(URL).mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, content=b"%PDF")]
    )
    assert await renderer.render("<p>x</p>") == b"%PDF"
    assert route.call_count == 2


@respx.mock
async def test_retries_a_server_error_once(renderer: GotenbergRenderer) -> None:
    respx.post(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, content=b"%PDF")])
    assert await renderer.render("<p>x</p>", footer_html="<p>f</p>") == b"%PDF"


@respx.mock
async def test_gives_up_after_two_timeouts(renderer: GotenbergRenderer) -> None:
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(PdfRenderError, match="timed out"):
        await renderer.render("<p>x</p>")


@respx.mock
async def test_client_errors_are_not_retried(renderer: GotenbergRenderer) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(400, text="bad html"))
    with pytest.raises(PdfRenderError, match="400"):
        await renderer.render("<p>x</p>")
    assert route.call_count == 1


@respx.mock
async def test_unreachable(renderer: GotenbergRenderer) -> None:
    respx.post(URL).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(PdfRenderError, match="unreachable"):
        await renderer.render("<p>x</p>")
