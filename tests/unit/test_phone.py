"""Tests de la normalisation des numéros de téléphone."""
from app.utils.phone import normalize_phone, phones_match


def test_normalize_national_format():
    assert normalize_phone("06 12 34 56 78") == "+33612345678"


def test_normalize_e164_unchanged():
    assert normalize_phone("+33612345678") == "+33612345678"


def test_normalize_empty_returns_none():
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def test_normalize_invalid_returns_none():
    assert normalize_phone("1234") is None


def test_phones_match_across_formats():
    assert phones_match("0612345678", "+33612345678")
    assert phones_match("06 12 34 56 78", "+33 6 12 34 56 78")


def test_phones_match_rejects_different_numbers():
    assert not phones_match("0612345678", "0698765432")


def test_phones_match_rejects_none():
    assert not phones_match(None, "+33612345678")
    assert not phones_match(None, None)
