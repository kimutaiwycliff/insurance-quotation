"""Template engine: Jinja2 (sandboxed, autoescape, StrictUndefined) → self-contained HTML (ADR-0014).

Self-contained means: fonts and images are inlined as data: URIs and every page carries a CSP that forbids all
fetches. The same HTML is the PDF source (Gotenberg) and the public-link web view (sandboxed iframe).
"""

import base64
import json
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Literal

from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment
from pydantic import BaseModel, ConfigDict

from app.core.money import Money
from app.modules.rendering.view import DOC_TITLES, BrandingView, DocumentView, FontPair

DOC_TYPES = tuple(DOC_TITLES)
__all__ = [
    "DOC_TITLES",
    "DOC_TYPES",
    "FONT_PAIRS",
    "TemplateManifest",
    "catalog",
    "render_footer",
    "render_html",
]

TEMPLATES_DIR = Path(__file__).parent / "templates"
FONTS_DIR = Path(__file__).parent / "fonts"

# No network, no scripts, no frames, no forms: inline styles, data: fonts and images only.
CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; "
    "base-uri 'none'; form-action 'none'; frame-ancestors *"
)


class TemplateManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    name: str
    description: str
    tier: Literal["free", "premium"]
    version: int
    doc_types: list[str]
    paper: Literal["A4", "Letter"] = "A4"
    font_pair: FontPair
    default_primary: str
    default_accent: str


class UnknownTemplateError(LookupError):
    pass


@cache
def catalog() -> dict[str, TemplateManifest]:
    manifests = {}
    for path in sorted(TEMPLATES_DIR.glob("*/manifest.json")):
        manifest = TemplateManifest.model_validate(json.loads(path.read_text()))
        if manifest.key != path.parent.name:
            raise ValueError(
                f"Manifest key {manifest.key!r} must match its folder {path.parent.name!r}"
            )
        manifests[manifest.key] = manifest
    return manifests


def manifest(key: str) -> TemplateManifest:
    try:
        return catalog()[key]
    except KeyError:
        raise UnknownTemplateError(key) from None


def _money(amount: Decimal | None, currency: str) -> str:
    if amount is None:
        return ""
    rounded = Money.of(amount, currency).rounded().amount
    return f"{currency} {rounded:,}"


def _quantity(value: Decimal) -> str:
    return f"{value.normalize():f}"  # 2 → "2", 2.50 → "2.5"


def _date(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else ""


class FontPairing(BaseModel):
    """A typeface pairing: body text, headings and figures, each with its bundled font files."""

    model_config = ConfigDict(frozen=True)

    name: str
    body: str
    display: str
    numbers: str
    files: tuple[tuple[str, int, str], ...]  # (family, weight, file name without .woff2)


_SANS = "'Noto Sans', Arial, sans-serif"
_SERIF = "Georgia, 'Times New Roman', serif"
_INTER = (("Inter", 400, "inter-400"), ("Inter", 600, "inter-600"), ("Inter", 700, "inter-700"))

FONT_PAIRS: dict[str, FontPairing] = {
    "sans": FontPairing(
        name="Modern sans",
        body=f"'Inter', {_SANS}",
        display=f"'Inter', {_SANS}",
        numbers=f"'Inter', {_SANS}",
        files=_INTER,
    ),
    "serif": FontPairing(
        name="Refined serif",
        body=f"'Inter', {_SANS}",
        display=f"'Source Serif 4', {_SERIF}",
        numbers=f"'Inter', {_SANS}",
        files=(
            *_INTER,
            ("Source Serif 4", 400, "source-serif-4-400"),
            ("Source Serif 4", 600, "source-serif-4-600"),
        ),
    ),
    "geometric": FontPairing(
        name="Geometric",
        body=f"'Inter', {_SANS}",
        display=f"'Manrope', 'Inter', {_SANS}",
        numbers=f"'Inter', {_SANS}",
        files=(*_INTER, ("Manrope", 600, "manrope-600"), ("Manrope", 800, "manrope-800")),
    ),
    "editorial": FontPairing(
        name="Editorial",
        body=f"'Inter', {_SANS}",
        display=f"'Fraunces', {_SERIF}",
        numbers=f"'Inter', {_SANS}",
        files=(*_INTER, ("Fraunces", 600, "fraunces-600"), ("Fraunces", 800, "fraunces-800")),
    ),
    "classic": FontPairing(
        name="Classic book",
        body=f"'Lora', {_SERIF}",
        display=f"'Lora', {_SERIF}",
        numbers=f"'Lora', {_SERIF}",
        files=(("Lora", 400, "lora-400"), ("Lora", 600, "lora-600"), ("Lora", 700, "lora-600")),
    ),
    "ledger": FontPairing(
        name="Ledger",
        body=f"'IBM Plex Sans', {_SANS}",
        display=f"'IBM Plex Sans', {_SANS}",
        numbers="'IBM Plex Mono', 'Courier New', monospace",
        files=(
            ("IBM Plex Sans", 400, "ibm-plex-sans-400"),
            ("IBM Plex Sans", 600, "ibm-plex-sans-600"),
            ("IBM Plex Sans", 700, "ibm-plex-sans-700"),
            ("IBM Plex Mono", 400, "ibm-plex-mono-400"),
            ("IBM Plex Mono", 600, "ibm-plex-mono-600"),
        ),
    ),
}

LOGO_HEIGHTS = {
    "small": (40, 150),
    "medium": (56, 200),
    "large": (84, 280),
}  # px: max height, max width


@cache
def _font_faces(pair: str) -> str:
    rules = []
    for family, weight, name in FONT_PAIRS[pair].files:
        data = base64.b64encode((FONTS_DIR / f"{name}.woff2").read_bytes()).decode()
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
            f"font-display:block;src:url(data:font/woff2;base64,{data}) format('woff2');}}"
        )
    return "\n".join(rules)


def _on_color(hex_color: str) -> str:
    """Black or white text, whichever contrasts more with ``hex_color`` (WCAG relative luminance)."""
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]  # noqa: PLR2004
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    return "#111111" if (luminance + 0.05) / 0.05 > 1.05 / (luminance + 0.05) else "#FFFFFF"


@cache
def _environment() -> ImmutableSandboxedEnvironment:
    env = ImmutableSandboxedEnvironment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["money"] = _money
    env.filters["qty"] = _quantity
    env.filters["date"] = _date
    return env


def render_html(key: str, view: DocumentView, branding: BrandingView) -> str:
    meta = manifest(key)
    if view.doc_type not in meta.doc_types:
        raise UnknownTemplateError(f"{key} does not support {view.doc_type}")
    template = _environment().get_template(f"{key}/document.html.j2")
    options = branding.options
    logo_height, logo_width = LOGO_HEIGHTS[options.logo_size]
    return template.render(
        doc=view,
        brand=branding,
        opts=options,
        on_primary=_on_color(branding.primary_color),
        on_accent=_on_color(branding.accent_color),
        title=DOC_TITLES[view.doc_type],
        csp=CSP,
        font_faces=_font_faces(branding.font_pair),
        fonts=FONT_PAIRS[branding.font_pair],
        logo_height=logo_height,
        logo_width=logo_width,
        initials=_initials(view.seller.name),
        paper=options.paper or meta.paper,
    )


def _initials(name: str) -> str:
    """Up to two initials for the seal, from the first letters of the first two words."""
    words = [w for w in name.replace("&", " ").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "•"


def render_footer(view: DocumentView, branding: BrandingView) -> str:
    return _environment().get_template("_footer.html.j2").render(doc=view, brand=branding, csp=CSP)
