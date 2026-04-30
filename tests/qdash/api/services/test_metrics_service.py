"""Tests for metrics_service helpers."""

from datetime import datetime

import pytest
from qdash.api.services.metrics_service import _parse_date_range
from starlette.exceptions import HTTPException


class TestParseDateRange:
    """Tests for _parse_date_range absolute date-range parsing."""

    def test_both_none_returns_none_pair(self):
        start, end = _parse_date_range(None, None)
        assert start is None
        assert end is None

    def test_empty_strings_become_none(self):
        start, end = _parse_date_range("", "")
        assert start is None
        assert end is None

    def test_whitespace_only_strings_become_none(self):
        start, end = _parse_date_range("   ", "\t\n")
        assert start is None
        assert end is None

    def test_empty_start_with_valid_end(self):
        start, end = _parse_date_range("", "2026-01-02T00:00:00+09:00")
        assert start is None
        assert isinstance(end, datetime)

    def test_valid_start_with_empty_end(self):
        start, end = _parse_date_range("2026-01-01T00:00:00+09:00", "")
        assert isinstance(start, datetime)
        assert end is None

    def test_valid_iso8601_pair(self):
        start, end = _parse_date_range(
            "2026-01-01T00:00:00+09:00",
            "2026-01-02T00:00:00+09:00",
        )
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        assert start < end

    def test_invalid_string_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_date_range("not-a-date", None)
        assert exc_info.value.status_code == 400

    def test_inverted_range_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_date_range(
                "2026-01-02T00:00:00+09:00",
                "2026-01-01T00:00:00+09:00",
            )
        assert exc_info.value.status_code == 400
        assert "start_at must be on or before end_at" in exc_info.value.detail
