"""Load and validate jurisdiction packs from YAML (read once per process; packs are code-reviewed data)."""

from functools import cache
from pathlib import Path

import yaml

from app.calc.pack import Pack

PACKS_DIR = Path(__file__).parent / "packs"


class UnknownPackError(LookupError):
    pass


@cache
def all_packs() -> dict[tuple[str, str], Pack]:
    packs: dict[tuple[str, str], Pack] = {}
    for path in sorted(PACKS_DIR.glob("*/*.yaml")):
        pack = Pack.model_validate(yaml.safe_load(path.read_text()))
        if (pack.code, pack.version) != (path.parent.name, path.stem):
            raise ValueError(f"{path}: code/version must match its folder and file name")
        packs[(pack.code, pack.version)] = pack
    return packs


def pack(code: str, version: str | None = None) -> Pack:
    """A specific version, or the latest version of ``code``."""
    candidates = {v: p for (c, v), p in all_packs().items() if c == code}
    if not candidates:
        raise UnknownPackError(code)
    if version is None:
        return candidates[max(candidates)]
    try:
        return candidates[version]
    except KeyError:
        raise UnknownPackError(f"{code} {version}") from None


def pack_for_country(country_code: str) -> Pack:
    try:
        return pack(country_code.lower())
    except UnknownPackError:
        return pack("generic")
