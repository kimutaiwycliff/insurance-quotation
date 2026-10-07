"""Document number patterns (pure; no I/O).

Tokens: ``{YYYY}`` ``{YY}`` ``{MM}`` ``{BRANCH}`` and ``{SEQ}`` / ``{SEQ:n}`` (zero-padded to ``n`` digits,
1-9). Everything else is literal and limited to ``A-Z a-z 0-9 - / _ .``. ``{SEQ}`` must appear exactly once.
Example: ``INV-{YYYY}-{SEQ:5}`` → ``INV-2026-00042``.
"""

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

MAX_PATTERN_LENGTH = 64
MAX_NUMBER_LENGTH = 40
_TOKEN = re.compile(r"\{([A-Z]+)(?::(\d))?\}")
_LITERAL = re.compile(r"^[A-Za-z0-9\-/_.]*$")
_KNOWN = {"YYYY", "YY", "MM", "BRANCH", "SEQ"}


class ResetPeriod(StrEnum):
    NEVER = "never"
    YEARLY = "yearly"
    MONTHLY = "monthly"


class InvalidPatternError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Pattern:
    raw: str

    @classmethod
    def parse(cls, raw: str) -> Pattern:
        if not raw or len(raw) > MAX_PATTERN_LENGTH:
            raise InvalidPatternError(f"Pattern must be 1-{MAX_PATTERN_LENGTH} characters")
        seq_count = 0
        for match in _TOKEN.finditer(raw):
            name, width = match.group(1), match.group(2)
            if name not in _KNOWN:
                raise InvalidPatternError(f"Unknown token {{{name}}}")
            if width is not None and (name != "SEQ" or int(width) == 0):
                raise InvalidPatternError("Only {SEQ:n} takes a width, and n must be 1-9")
            seq_count += name == "SEQ"
        if seq_count != 1:
            raise InvalidPatternError("Pattern must contain {SEQ} exactly once")
        if not _LITERAL.match(_TOKEN.sub("", raw)):
            raise InvalidPatternError("Literal text may only use letters, digits and - / _ .")
        return cls(raw)

    def uses_branch(self) -> bool:
        return "{BRANCH}" in self.raw

    def format(self, *, seq: int, on: date, branch_code: str | None = None) -> str:
        if seq < 1:
            raise ValueError("Sequence numbers start at 1")
        if self.uses_branch() and not branch_code:
            raise InvalidPatternError("Pattern uses {BRANCH} but no branch was given")

        def replace(match: re.Match[str]) -> str:
            name, width = match.group(1), match.group(2)
            match name:
                case "YYYY":
                    return f"{on.year:04d}"
                case "YY":
                    return f"{on.year % 100:02d}"
                case "MM":
                    return f"{on.month:02d}"
                case "BRANCH":
                    return branch_code or ""
                case _:
                    return str(seq).zfill(int(width or 1))

        number = _TOKEN.sub(replace, self.raw)
        if len(number) > MAX_NUMBER_LENGTH:
            raise InvalidPatternError(f"Formatted number exceeds {MAX_NUMBER_LENGTH} characters")
        return number


def period_key(reset: ResetPeriod, on: date) -> str:
    """Bucket in which the sequence counts; a new bucket restarts at the scheme's start value."""
    match reset:
        case ResetPeriod.NEVER:
            return "all"
        case ResetPeriod.YEARLY:
            return f"{on.year:04d}"
        case ResetPeriod.MONTHLY:
            return f"{on.year:04d}-{on.month:02d}"
