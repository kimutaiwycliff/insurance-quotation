"""Short payment references for M-Pesa STK/C2B (SPEC_REVIEW P4: AccountReference ≤ 12 characters).

Format: 9 random characters + 1 check character from an alphabet without look-alikes (no 0/O, 1/I/L), so a
client can read it over the phone and a typo is caught before a payment is mis-allocated.

Check character: ``sum(position_weight * value) mod 31`` with weights 1..9. Because 31 is prime and the weights
are distinct and non-zero, every single-character error and every adjacent swap in the body changes the sum
(Luhn mod N would not do: it needs an even alphabet size, and ours has 31 characters).
"""

import secrets

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
BODY_LENGTH = 9
LENGTH = BODY_LENGTH + 1
_INDEX = {ch: i for i, ch in enumerate(ALPHABET)}
_N = len(ALPHABET)


def _check_char(body: str) -> str:
    total = sum(weight * _INDEX[ch] for weight, ch in enumerate(body, start=1))
    return ALPHABET[total % _N]


def generate_payment_reference() -> str:
    body = "".join(secrets.choice(ALPHABET) for _ in range(BODY_LENGTH))
    return body + _check_char(body)


def normalise(reference: str) -> str:
    """Accept what people type: lower case, spaces and dashes."""
    return reference.upper().replace(" ", "").replace("-", "")


def is_valid_payment_reference(reference: str) -> bool:
    ref = normalise(reference)
    if len(ref) != LENGTH or any(ch not in _INDEX for ch in ref):
        return False
    return _check_char(ref[:-1]) == ref[-1]
