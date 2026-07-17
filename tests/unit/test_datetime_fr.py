"""Tests du formatage des dates en français parlé."""
import pytest

from app.utils.datetime_fr import format_date_fr, format_datetime_fr


def test_format_utc_converted_to_paris_summer():
    # 14h30 UTC en juillet = 16h30 à Paris (UTC+2)
    assert format_datetime_fr("2026-07-19T14:30:00Z") == "dimanche 19 juillet à 16h30"


def test_format_naive_datetime_assumed_paris():
    assert format_datetime_fr("2026-07-19T14:00:00") == "dimanche 19 juillet à 14h"


def test_format_first_day_of_month():
    assert format_datetime_fr("2026-08-01T09:05:00") == "samedi premier août à 9h05"


def test_format_whole_hour_has_no_minutes():
    result = format_datetime_fr("2026-07-20T10:00:00")
    assert result.endswith("à 10h")
    assert "10h00" not in result


def test_format_date_only():
    assert format_date_fr("2026-07-19T14:00:00") == "dimanche 19 juillet"


def test_unparsable_value_returned_as_is():
    assert format_datetime_fr("pas une date") == "pas une date"
