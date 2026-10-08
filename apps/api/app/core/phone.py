"""Phone numbers in E.164. Kenyan numbers are accepted the way people write them (0712 345 678, 712345678,
254712345678, +254 712 345 678); other countries need the international prefix."""

import re

_DIGITS = re.compile(r"[^\d+]")
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
NATIONAL_LENGTH = 10  # 0712345678
SUBSCRIBER_LENGTH = 9  # 712345678


class InvalidPhoneError(ValueError):
    pass


def to_e164(raw: str, default_country_code: str = "254") -> str:
    value = _DIGITS.sub("", raw.strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("+"):
        candidate = value
    elif value.startswith(default_country_code) and len(value) >= len(default_country_code) + 9:
        candidate = "+" + value
    elif value.startswith("0") and len(value) == NATIONAL_LENGTH:  # 0712345678 → +254712345678
        candidate = f"+{default_country_code}{value[1:]}"
    elif (
        len(value) == SUBSCRIBER_LENGTH and value[0] in "17"
    ):  # 712345678 / 112345678 (Safaricom 01xx)
        candidate = f"+{default_country_code}{value}"
    else:
        raise InvalidPhoneError("Enter a phone number like 0712 345 678 or +256 772 123 456")
    if not E164.match(candidate):
        raise InvalidPhoneError("Enter a phone number like 0712 345 678 or +256 772 123 456")
    return candidate
