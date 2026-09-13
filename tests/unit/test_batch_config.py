"""Unit tests for MAX_BATCH_SUBAGENTS parsing (spec 020, US2)."""

from src.config import MAX_BATCH_SUBAGENTS_DEFAULT, parse_positive_int


def test_default_when_unset():
    assert parse_positive_int("", MAX_BATCH_SUBAGENTS_DEFAULT) == MAX_BATCH_SUBAGENTS_DEFAULT
    assert MAX_BATCH_SUBAGENTS_DEFAULT == 5


def test_valid_override():
    assert parse_positive_int("3", 5) == 3


def test_whitespace_is_trimmed():
    assert parse_positive_int(" 4 ", 5) == 4


def test_zero_falls_back_to_default():
    assert parse_positive_int("0", 5) == 5


def test_negative_falls_back_to_default():
    assert parse_positive_int("-2", 5) == 5


def test_non_integer_falls_back_to_default():
    assert parse_positive_int("abc", 5) == 5
