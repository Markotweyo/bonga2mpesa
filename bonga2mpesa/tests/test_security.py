import pytest
from app.core.security import sanitize_phone, is_valid_kenyan_phone


@pytest.mark.parametrize("raw,expected", [
    ("0712345678", "254712345678"),
    ("+254712345678", "254712345678"),
    ("254712345678", "254712345678"),
    ("712345678", "254712345678"),
])
def test_sanitize_phone(raw, expected):
    assert sanitize_phone(raw) == expected


@pytest.mark.parametrize("phone", [
    "0712345678",
    "+254712345678",
    "254712345678",
    "0110123456",
])
def test_valid_kenyan_phones(phone):
    assert is_valid_kenyan_phone(phone) is True


@pytest.mark.parametrize("phone", [
    "123",
    "abcdefghij",
    "25471234",       # too short
    "2541234567890",  # too long
])
def test_invalid_kenyan_phones(phone):
    assert is_valid_kenyan_phone(phone) is False
