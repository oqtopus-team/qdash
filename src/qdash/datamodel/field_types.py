"""Annotated field types shared by domain models, documents, and API schemas."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer

from qdash.common.utils.datetime import ensure_timezone, format_elapsed_time, parse_elapsed_time


def _serialize_elapsed_time(value: timedelta | None) -> str | None:
    """Serialize an elapsed time to H:MM:SS, or None when it is empty."""
    return format_elapsed_time(value) if value else None


def _elapsed_seconds(value: Any) -> float | None:
    """Parse an elapsed time from any supported format into seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, timedelta):
        return value.total_seconds()
    parsed = parse_elapsed_time(value)
    return parsed.total_seconds() if parsed else None


def _ensure_timezone(value: Any) -> Any:
    """Make datetimes timezone-aware and leave other inputs to pydantic."""
    if isinstance(value, datetime):
        return ensure_timezone(value)
    return value


ElapsedTime = Annotated[
    timedelta | None,
    BeforeValidator(parse_elapsed_time),
    PlainSerializer(_serialize_elapsed_time, return_type=str | None),
]
"""Elapsed time parsed from seconds, a timedelta, or H:MM:SS and serialized as H:MM:SS."""

ElapsedSeconds = Annotated[float | None, BeforeValidator(_elapsed_seconds)]
"""Elapsed time stored as seconds, accepting the same inputs as ``ElapsedTime``."""

TimezoneAwareDatetime = Annotated[datetime | None, BeforeValidator(_ensure_timezone)]
"""Optional datetime normalized to a timezone-aware value on validation."""
