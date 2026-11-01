from src.csv_utils import parse_csv


def test_single_value_is_unchanged():
    assert parse_csv("https://app.example.com") == ["https://app.example.com"]


def test_multiple_values_are_split_and_trimmed():
    assert parse_csv(" https://a.com ,https://b.com,, ") == ["https://a.com", "https://b.com"]


def test_wildcard_and_empty_mean_allow_all():
    assert parse_csv("*") == ["*"]
    assert parse_csv("") == ["*"]
    assert parse_csv(None) == ["*"]
    assert parse_csv("https://a.com,*") == ["*"]
