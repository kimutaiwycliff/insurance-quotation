"""Document designs (rendering module): every design, every option, logo or none, insurance comparisons."""

from decimal import Decimal

import pytest

from app.modules.rendering import engine
from app.modules.rendering.fixtures import sample_view
from app.modules.rendering.view import (
    AmountLine,
    BrandingView,
    DesignOptions,
    DocumentView,
    OptionView,
)

DESIGNS = sorted(engine.catalog())
LOGO = "data:image/png;base64,iVBORw0KGgo="


def _comparison_quote() -> DocumentView:
    options = [
        OptionView(
            position=i,
            insurer=insurer,
            product="Motor private comprehensive",
            premium=Decimal(premium),
            charges=[AmountLine(label="Training levy", amount=Decimal("140"))],
            total=Decimal(premium) + 140,
            recommended=i == 1,
        )
        for i, (insurer, premium) in enumerate(
            [("Rift Assurance", "70000"), ("Savanna General", "80000")], 1
        )
    ]
    return sample_view("quote").model_copy(update={"options": options, "lines": [], "totals": None})


@pytest.mark.parametrize("key", DESIGNS)
class TestEveryDesign:
    def test_insurance_comparison_quote(self, key: str) -> None:
        html = engine.render_html(key, _comparison_quote(), BrandingView())
        assert "Rift Assurance" in html
        assert "Choose one option" in html

    def test_without_a_logo_the_agency_name_stands_in(self, key: str) -> None:
        view = sample_view("invoice")
        html = engine.render_html(key, view, BrandingView(logo_data_uri=None))
        assert 'class="logo"' not in html
        assert view.seller.name in html

    def test_with_a_logo(self, key: str) -> None:
        html = engine.render_html(key, sample_view("invoice"), BrandingView(logo_data_uri=LOGO))
        assert LOGO in html

    def test_options(self, key: str) -> None:
        opts = DesignOptions(
            logo_align="center",
            logo_size="large",
            show_signature=True,
            seal_watermark=True,
            paper="Letter",
        )
        html = engine.render_html(key, sample_view("invoice"), BrandingView(options=opts))
        assert '<body class="logo-center">' in html
        assert "size: Letter" in html
        assert "--logo-h: 84px" in html
        assert "Authorised signature" in html
        assert 'class="seal-wm"' in html

    def test_payment_box_can_be_hidden(self, key: str) -> None:
        shown = engine.render_html(key, sample_view("invoice"), BrandingView())
        hidden = engine.render_html(
            key, sample_view("invoice"), BrandingView(options=DesignOptions(show_payment=False))
        )
        heading = '<h3 class="h3">How to pay</h3>'
        assert heading in shown
        assert heading not in hidden

    @pytest.mark.parametrize("pair", sorted(engine.FONT_PAIRS))
    def test_every_font_pairing(self, key: str, pair: str) -> None:
        html = engine.render_html(key, sample_view("quote"), BrandingView(font_pair=pair))  # type: ignore[arg-type]
        for family, _, _ in engine.FONT_PAIRS[pair].files:
            assert f"font-family:'{family}'" in html
        assert "http://" not in html
        assert "https://" not in html


def test_designs_default_to_their_own_paper_and_alignment() -> None:
    html = engine.render_html("executive", sample_view("quote"), BrandingView())
    assert '<body class="logo-auto">' in html
    assert "size: A4" in html


def test_corporate_always_has_signature_lines() -> None:
    html = engine.render_html("corporate", sample_view("invoice"), BrandingView())
    assert "Authorised signature" in html


def test_seal_design_draws_the_agency_seal_without_a_logo() -> None:
    view = sample_view("invoice")
    html = engine.render_html("seal", view, BrandingView())
    assert f"{view.seller.name} seal" in html


@pytest.mark.parametrize(
    ("name", "initials"),
    [("Wanjiku Insurance Agency", "WI"), ("Acacia & Sons", "AS"), ("Otieno", "O"), ("", "•")],
)
def test_seal_initials(name: str, initials: str) -> None:
    assert engine._initials(name) == initials


def test_every_bundled_font_file_exists() -> None:
    for pairing in engine.FONT_PAIRS.values():
        for _, _, name in pairing.files:
            assert (engine.FONTS_DIR / f"{name}.woff2").read_bytes()[:4] == b"wOF2"
