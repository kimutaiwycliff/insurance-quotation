"""M2 pure logic: upload sniffing, template engine safety, message templates, link helpers."""

import re
import uuid

import pytest
from markupsafe import escape

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.modules.documents.sniff import UnsupportedFileError, sniff, type_for_filename, verify
from app.modules.messaging import catalog
from app.modules.messaging.service import read_unsubscribe_token, unsubscribe_token
from app.modules.public_links.service import hash_ip, hash_token, is_bot
from app.modules.rendering import engine
from app.modules.rendering.fixtures import VARIANTS, sample_view
from app.modules.rendering.view import BrandingView, Party

PDF = b"%PDF-1.7\n..."
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8


class TestSniff:
    @pytest.mark.parametrize(
        ("name", "head", "expected"),
        [
            ("id.pdf", PDF, "application/pdf"),
            ("ID.PNG", PNG, "image/png"),
            ("photo.jpeg", JPEG, "image/jpeg"),
            ("img.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
            ("img.heic", b"\x00\x00\x00\x18ftypheic", "image/heic"),
            (
                "book.xlsx",
                b"PK\x03\x04rest",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            ("list.csv", b"name,amount\nWanjiku,100\n", "text/csv"),
        ],
    )
    def test_accepts_matching_content(self, name: str, head: bytes, expected: str) -> None:
        assert verify(name, head) == expected

    @pytest.mark.parametrize(
        ("name", "head"),
        [
            ("invoice.pdf", PNG),  # renamed image
            ("photo.png", b"<html><script>"),  # HTML disguised as image
            ("list.csv", b"\x00\x01binary"),
            ("evil.html", b"<html>"),  # extension not allowed
            ("noext", PDF),
            ("x.exe", b"MZ"),
        ],
    )
    def test_rejects(self, name: str, head: bytes) -> None:
        with pytest.raises(UnsupportedFileError):
            verify(name, head)

    def test_unknown_bytes(self) -> None:
        assert sniff(b"") is None
        assert sniff(b"\xff\xfe\x00") is None
        assert type_for_filename("A.PDF").extension == "pdf"


class TestTemplates:
    def test_catalog(self) -> None:
        tiers = sorted(m.tier for m in engine.catalog().values())
        assert tiers == ["free", "premium", "premium"]  # plan M2: 1 free + 2 premium

    @pytest.mark.parametrize("key", ["classic", "savanna", "executive"])
    @pytest.mark.parametrize("doc_type", ["quote", "invoice", "receipt", "credit_note"])
    def test_every_template_renders_every_document(self, key: str, doc_type: str) -> None:
        html = engine.render_html(key, sample_view(doc_type), BrandingView())  # type: ignore[arg-type]
        assert str(escape(engine.CSP)) in html
        assert "QT-2026-00042" in html or "-2026-00042" in html
        assert "http://" not in html  # nothing to fetch
        assert "https://" not in html

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_fixture_sets(self, variant: str) -> None:
        html = engine.render_html("classic", sample_view("invoice", variant), BrandingView())  # type: ignore[arg-type]
        if variant == "zero_dp":
            assert "UGX 1,850,000<" in html  # no decimals for UGX
        if variant == "many_lines":
            assert html.count("<tr>") >= 150

    def test_tenant_text_is_escaped(self) -> None:
        hostile = '"><img src=x onerror=alert(1)><script>alert(1)</script>'
        view = sample_view("invoice").model_copy(
            update={"seller": Party(name=hostile), "notes": hostile}
        )
        html = engine.render_html("savanna", view, BrandingView(footer_text=hostile))
        assert "<script>alert" not in html
        assert "<img src=x" not in html
        assert "&lt;script&gt;" in html

    def test_branding_colours_and_logo_are_validated(self) -> None:
        with pytest.raises(ValueError, match="pattern"):
            BrandingView(primary_color="red;}body{display:none")
        with pytest.raises(ValueError, match="pattern"):
            BrandingView(logo_data_uri="javascript:alert(1)")

    @pytest.mark.parametrize(
        ("color", "text"), [("#FFFFFF", "#111111"), ("#000000", "#FFFFFF"), ("#1F4E79", "#FFFFFF")]
    )
    def test_text_colour_contrasts_with_brand(self, color: str, text: str) -> None:
        assert engine._on_color(color) == text

    def test_unknown_template(self) -> None:
        with pytest.raises(engine.UnknownTemplateError):
            engine.manifest("nope")


class TestMessageTemplates:
    @pytest.mark.parametrize("event", list(catalog.CATALOG))
    def test_builtins_render_with_their_sample(self, event: str) -> None:
        t = catalog.CATALOG[event]
        subject, body = catalog.render(t.subject, t.body, t.sample)
        assert subject
        assert body

    def test_missing_variable_fails(self) -> None:
        with pytest.raises(catalog.TemplateRenderError):
            catalog.render("{{ nope }}", "x", {})

    def test_sandbox_blocks_attribute_tricks(self) -> None:
        with pytest.raises(catalog.TemplateRenderError):
            catalog.render("x", "{{ ''.__class__.__mro__[1].__subclasses__() }}", {})

    def test_subject_is_single_line(self) -> None:
        subject, _ = catalog.render("Hi\r\nBcc: victim@example.com {{ a }}", "b", {"a": "x"})
        assert "\n" not in subject
        assert "\r" not in subject


class TestUnsubscribeToken:
    def test_round_trip_and_forgery(self, unit_settings: Settings) -> None:
        tenant = uuid.uuid4()
        token = unsubscribe_token(tenant, "Otieno@Example.com", "reminders", unit_settings)
        assert read_unsubscribe_token(token, unit_settings) == (
            tenant,
            "otieno@example.com",
            "reminders",
        )
        body, _, _ = token.partition(".")
        for forged in (f"{body}.AAAAAAAAAAAAAAAAAAAAAA", "garbage", token[:-2] + "xx"):
            with pytest.raises(NotFoundError):
                read_unsubscribe_token(forged, unit_settings)


class TestLinkHelpers:
    @pytest.mark.parametrize(
        ("ua", "bot"),
        [
            (
                "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/129 Mobile Safari/537.36",
                False,
            ),
            ("WhatsApp/2.24.1 A", True),
            ("facebookexternalhit/1.1", True),
            ("Googlebot/2.1", True),
            ("curl/8.0", True),
            (None, True),
        ],
    )
    def test_bot_detection(self, ua: str | None, bot: bool) -> None:
        assert is_bot(ua) is bot

    def test_hashes(self, unit_settings: Settings) -> None:
        assert len(hash_token("x")) == 32
        ip = hash_ip("10.0.0.1", unit_settings)
        assert ip is not None
        assert re.fullmatch(r"[0-9a-f]{32}", ip)
        assert hash_ip(None, unit_settings) is None
