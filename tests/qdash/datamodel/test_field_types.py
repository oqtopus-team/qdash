"""Tests for the shared annotated field types."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from qdash.datamodel.field_types import ElapsedSeconds, ElapsedTime, TimezoneAwareDatetime


class _Model(BaseModel):
    elapsed: ElapsedTime = None
    seconds: ElapsedSeconds = None
    at: TimezoneAwareDatetime = None


def test_elapsed_time_parses_inputs_and_serializes_as_hms() -> None:
    assert _Model.model_validate({"elapsed": "0:01:05"}).elapsed == timedelta(seconds=65)
    assert _Model.model_validate({"elapsed": 90}).elapsed == timedelta(seconds=90)
    assert (
        _Model.model_validate({"elapsed": timedelta(hours=1, seconds=2)}).model_dump()["elapsed"]
        == "1:00:02"
    )
    assert (
        _Model.model_validate({"elapsed": timedelta(0)}).model_dump(mode="json")["elapsed"] is None
    )
    assert _Model().model_dump()["elapsed"] is None


def test_elapsed_seconds_accepts_every_elapsed_time_format() -> None:
    assert _Model.model_validate({"seconds": 3}).seconds == 3.0
    assert _Model.model_validate({"seconds": timedelta(minutes=2)}).seconds == 120.0
    assert _Model.model_validate({"seconds": "0:00:30"}).seconds == 30.0
    assert _Model.model_validate({"seconds": None}).seconds is None


def test_timezone_aware_datetime_normalizes_naive_values() -> None:
    naive = _Model.model_validate({"at": datetime(2026, 1, 2, 3, 4, 5)}).at
    assert naive is not None
    assert naive.tzinfo is not None
    assert _Model.model_validate({"at": "2026-01-02T03:04:05+00:00"}).at == datetime(
        2026, 1, 2, 3, 4, 5, tzinfo=UTC
    )
