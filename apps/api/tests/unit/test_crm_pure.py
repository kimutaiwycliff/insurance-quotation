"""PII encryption and phone normalisation."""

import pytest

from app.core.config import Settings
from app.core.crypto import CryptoConfigError, DecryptionError, _build, mask, pii_cipher
from app.core.phone import InvalidPhoneError, to_e164


class TestPiiCipher:
    def test_round_trip_and_randomised(self, unit_settings: Settings) -> None:
        cipher = pii_cipher(unit_settings)
        a, b = cipher.encrypt("12345678"), cipher.encrypt("12345678")
        assert a != b  # random nonce
        assert a.startswith("dev1:")
        assert cipher.decrypt(a) == "12345678"
        assert "12345678" not in a

    def test_lookup_hash_ignores_formatting(self, unit_settings: Settings) -> None:
        cipher = pii_cipher(unit_settings)
        assert cipher.lookup_hash("A 123-456 7") == cipher.lookup_hash("a1234567")
        assert cipher.lookup_hash("A1234567") != cipher.lookup_hash("A1234568")

    def test_key_rotation(self) -> None:
        old = _build("k1:" + "QUFB" * 10 + "QUE=", "l" * 32)
        token = old.encrypt("secret")
        rotated = _build("k2:" + "QkJC" * 10 + "QkI=" + ",k1:" + "QUFB" * 10 + "QUE=", "l" * 32)
        assert rotated.decrypt(token) == "secret"  # old data still readable
        assert rotated.encrypt("x").startswith("k2:")  # new data uses the new key

    def test_tampering_and_unknown_keys(self, unit_settings: Settings) -> None:
        cipher = pii_cipher(unit_settings)
        token = cipher.encrypt("12345678")
        with pytest.raises(DecryptionError):
            cipher.decrypt(token[:-4] + "AAAA")
        with pytest.raises(DecryptionError):
            cipher.decrypt("nope:" + token.split(":", 1)[1])

    @pytest.mark.parametrize("spec", ["", "k1:short", ":QUFB"])
    def test_bad_config(self, spec: str) -> None:
        with pytest.raises(CryptoConfigError):
            _build(spec, "l" * 32)

    def test_mask(self) -> None:
        assert mask("12 345 678") == "•••••678"
        assert mask(None) is None


class TestPhones:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0712 345 678", "+254712345678"),
            ("712345678", "+254712345678"),
            ("0112-345-678", "+254112345678"),
            ("254712345678", "+254712345678"),
            ("+254 712 345 678", "+254712345678"),
            ("00256772123456", "+256772123456"),
            ("+44 20 7946 0958", "+442079460958"),
        ],
    )
    def test_normalises(self, raw: str, expected: str) -> None:
        assert to_e164(raw) == expected

    @pytest.mark.parametrize("raw", ["", "12", "abc", "0712", "+0712345678"])
    def test_rejects(self, raw: str) -> None:
        with pytest.raises(InvalidPhoneError):
            to_e164(raw)
