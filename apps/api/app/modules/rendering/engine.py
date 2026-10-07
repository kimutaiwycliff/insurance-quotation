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
from app.modules.rendering.view import DOC_TITLES, BrandingView, DocumentView

DOC_TYPES = tuple(DOC_TITLES)
__all__ = ["DOC_TITLES", "DOC_TYPES", "TemplateManifest", "catalog", "render_footer", "render_html"]

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
    font_pair: Literal["sans", "serif"]
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


@cache
def _font_faces(pair: str) -> str:
    files = (
        [("Inter", 400, "inter-400"), ("Inter", 600, "inter-600"), ("Inter", 700, "inter-700")]
        if pair == "sans"
        else [
            ("Inter", 400, "inter-400"),
            ("Inter", 600, "inter-600"),
            ("Source Serif 4", 400, "source-serif-4-400"),
            ("Source Serif 4", 600, "source-serif-4-600"),
        ]
    )
    rules = []
    for family, weight, name in files:
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
    return template.render(
        doc=view,
        brand=branding,
        on_primary=_on_color(branding.primary_color),
        title=DOC_TITLES[view.doc_type],
        csp=CSP,
        font_faces=_font_faces(branding.font_pair),
        paper=meta.paper,
    )


def render_footer(view: DocumentView, branding: BrandingView) -> str:
    return _environment().get_template("_footer.html.j2").render(doc=view, brand=branding, csp=CSP)
