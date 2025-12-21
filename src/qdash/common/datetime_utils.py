"""Datetime utilities for QDash application.

This module provides centralized datetime handling with consistent timezone support.
All datetime operations should use these utilities to ensure consistency across the application.

Design decisions:
- All datetimes are stored in the configured timezone (default: Asia/Tokyo)
- pendulum is used for timezone-aware datetime operations
- Standard datetime objects are used for MongoDB compatibility
"""

from datetime import datetime, timedelta
from functools import lru_cache

import pendulum
from pendulum import DateTime as PendulumDateTime

DEFAULT_TIMEZONE = "Asia/Tokyo"


@lru_cache(maxsize=1)
def get_timezone() -> str:
    """Get the configured timezone.

    Returns
    -------
        str: Timezone string (e.g., "Asia/Tokyo")

    """
    try:
        from qdash.config import get_settings

        return getattr(get_settings(), "timezone", DEFAULT_TIMEZONE)
    except Exception:
        return DEFAULT_TIMEZONE


def now() -> datetime:
    """Get current datetime in the configured timezone.

    Returns a timezone-aware standard datetime object in the configured timezone.

    Returns
    -------
        datetime: Current datetime in configured timezone

    """
    tz = get_timezone()
    pdt = pendulum.now(tz)
    # Convert to standard datetime for JSON serialization compatibility
    return datetime(
        pdt.year,
        pdt.month,
        pdt.day,
        pdt.hour,
        pdt.minute,
        pdt.second,
        pdt.microsecond,
        tzinfo=pdt.tzinfo,
    )


def now_iso() -> str:
    """Get current datetime as ISO8601 string.

    Returns
    -------
        str: Current datetime in ISO8601 format

    """
    return now().isoformat()


def ensure_timezone(value: datetime | None) -> datetime | None:
    """Ensure datetime is timezone-aware.

    MongoDB returns naive datetimes (assumed UTC). This function converts them
    to timezone-aware datetimes in UTC, which can then be compared with other
    timezone-aware datetimes.

    Args:
    ----
        value: datetime that may or may not have timezone info

    Returns:
    -------
        datetime: Timezone-aware datetime, or None if input is None

    """
    if value is None:
        return None
    if value.tzinfo is not None:
        # Convert pendulum DateTime to standard datetime for JSON serialization
        if isinstance(value, PendulumDateTime):
            return datetime(
                value.year,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
                value.microsecond,
                tzinfo=value.tzinfo,
            )
        return value
    # Naive datetime from MongoDB is in UTC - convert to standard datetime with UTC
    from datetime import timezone as dt_timezone

    return value.replace(tzinfo=dt_timezone.utc)


def to_datetime(value: str | datetime | PendulumDateTime | None) -> datetime | None:
    """Convert various datetime representations to datetime object.

    Args:
    ----
        value: String (ISO8601), datetime, or pendulum DateTime

    Returns:
    -------
        datetime: Converted datetime object, or None if input is None

    """
    if value is None:
        return None
    if isinstance(value, PendulumDateTime):
        return datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            tzinfo=value.tzinfo,
        )
    if isinstance(value, datetime):
        return ensure_timezone(value)
    if isinstance(value, str):
        parsed = pendulum.parse(value)
        if isinstance(parsed, PendulumDateTime):
            return datetime(
                parsed.year,
                parsed.month,
                parsed.day,
                parsed.hour,
                parsed.minute,
                parsed.second,
                parsed.microsecond,
                tzinfo=parsed.tzinfo,
            )
        raise ValueError(f"Cannot parse datetime string: {value}")
    raise TypeError(f"Unsupported type for datetime conversion: {type(value)}")


def to_pendulum(value: str | datetime | PendulumDateTime | None) -> PendulumDateTime | None:
    """Convert various datetime representations to pendulum DateTime.

    Args:
    ----
        value: String (ISO8601), datetime, or pendulum DateTime

    Returns:
    -------
        PendulumDateTime: Converted pendulum DateTime, or None if input is None

    """
    if value is None:
        return None
    if isinstance(value, PendulumDateTime):
        return value
    if isinstance(value, datetime):
        return pendulum.instance(value)
    if isinstance(value, str):
        parsed = pendulum.parse(value)
        if isinstance(parsed, PendulumDateTime):
            return parsed
        raise ValueError(f"Cannot parse datetime string: {value}")
    raise TypeError(f"Unsupported type for pendulum conversion: {type(value)}")


def format_iso(dt: datetime | PendulumDateTime | None) -> str | None:
    """Format datetime as ISO8601 string.

    Args:
    ----
        dt: datetime or pendulum DateTime object

    Returns:
    -------
        str: ISO8601 formatted string, or None if input is None

    """
    if dt is None:
        return None
    return dt.isoformat()


def calculate_elapsed_time(start: datetime, end: datetime) -> timedelta:
    """Calculate elapsed time between two datetimes.

    Handles mixed timezone-aware and naive datetimes by normalizing both.
    Naive datetimes are assumed to be in the configured timezone.

    Args:
    ----
        start: Start datetime
        end: End datetime

    Returns:
    -------
        timedelta: Elapsed time

    """
    tz = get_timezone()
    # Normalize both to pendulum instances for consistent timezone handling
    start_p = pendulum.instance(start) if start.tzinfo else pendulum.instance(start, tz=tz)
    end_p = pendulum.instance(end) if end.tzinfo else pendulum.instance(end, tz=tz)
    diff = end_p.diff(start_p)
    return timedelta(seconds=diff.in_seconds())


def format_elapsed_time(elapsed: timedelta) -> str:
    """Format elapsed time as human-readable string.

    Args:
    ----
        elapsed: Elapsed time as timedelta

    Returns:
    -------
        str: Formatted elapsed time (e.g., "1:23:45" or "0:00:30")

    """
    total_seconds = int(elapsed.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


MAX_ELAPSED_TIME_STRING_LENGTH = 100  # Prevent DoS from extremely long strings
MAX_ELAPSED_TIME_SECONDS = 365 * 24 * 3600  # 1 year maximum


def parse_elapsed_time(elapsed_str: str | timedelta | int | float | None) -> timedelta | None:
    """Parse elapsed time string to timedelta.

    Supports multiple formats:
    - "1:23:45" (HH:MM:SS)
    - "23:45" (MM:SS)
    - "38 seconds", "38 second"
    - "1 minute", "13 minutes"
    - "1 hour", "2 hours"
    - "1 hour 30 minutes"
    - timedelta objects (pass through)
    - int/float (interpreted as seconds)

    Input validation:
    - String inputs are limited to MAX_ELAPSED_TIME_STRING_LENGTH characters
    - Parsed values are capped at MAX_ELAPSED_TIME_SECONDS (1 year)
    - Negative values raise ValueError

    Args:
    ----
        elapsed_str: Elapsed time string, timedelta, or number of seconds

    Returns:
    -------
        timedelta: Parsed elapsed time, or None if input is None

    Raises:
    ------
        ValueError: If string is too long, value is negative, or exceeds maximum

    """
    import re

    if elapsed_str is None:
        return None
    if isinstance(elapsed_str, timedelta):
        total_seconds = elapsed_str.total_seconds()
        if total_seconds < 0:
            raise ValueError("Elapsed time cannot be negative")
        if total_seconds > MAX_ELAPSED_TIME_SECONDS:
            raise ValueError(f"Elapsed time exceeds maximum ({MAX_ELAPSED_TIME_SECONDS} seconds)")
        return elapsed_str
    if isinstance(elapsed_str, (int, float)):
        if elapsed_str < 0:
            raise ValueError("Elapsed time cannot be negative")
        if elapsed_str > MAX_ELAPSED_TIME_SECONDS:
            raise ValueError(f"Elapsed time exceeds maximum ({MAX_ELAPSED_TIME_SECONDS} seconds)")
        return timedelta(seconds=elapsed_str)

    elapsed_str = str(elapsed_str).strip()
    if not elapsed_str:
        return None

    # Validate string length
    if len(elapsed_str) > MAX_ELAPSED_TIME_STRING_LENGTH:
        raise ValueError(
            f"Elapsed time string too long ({len(elapsed_str)} > {MAX_ELAPSED_TIME_STRING_LENGTH})"
        )

    # Try HH:MM:SS or MM:SS format first
    parts = elapsed_str.split(":")
    if len(parts) == 3:
        try:
            hours, minutes, seconds = map(int, parts)
            return timedelta(hours=hours, minutes=minutes, seconds=seconds)
        except ValueError:
            pass
    if len(parts) == 2:
        try:
            minutes, seconds = map(int, parts)
            return timedelta(minutes=minutes, seconds=seconds)
        except ValueError:
            pass

    # Parse human-readable format like "38 seconds", "1 minute", "2 hours 30 minutes"
    total_seconds = 0.0

    # Match patterns like "38 seconds", "1.5 hours", etc.
    # Use word boundaries and order from longest to shortest to avoid overlap
    patterns = [
        (r"([\d.]+)\s*(?:seconds|second)\b", 1),
        (r"([\d.]+)\s*(?:minutes|minute)\b", 60),
        (r"([\d.]+)\s*(?:hours|hour)\b", 3600),
        (r"([\d.]+)\s*secs?\b", 1),
        (r"([\d.]+)\s*mins?\b", 60),
        (r"([\d.]+)\s*hrs?\b", 3600),
    ]

    matched = False
    for pattern, multiplier in patterns:
        for match in re.finditer(pattern, elapsed_str, re.IGNORECASE):
            total_seconds += float(match.group(1)) * multiplier
            matched = True

    if matched:
        return timedelta(seconds=total_seconds)

    # Handle approximate formats from pendulum (no numbers)
    # These formats may appear in legacy data or from pendulum.diff().in_words()
    lower_str = elapsed_str.lower()
    if "few second" in lower_str:
        return timedelta(seconds=5)
    if "second" in lower_str:
        return timedelta(seconds=1)
    if "minute" in lower_str:
        return timedelta(minutes=1)
    if "hour" in lower_str:
        return timedelta(hours=1)

    # Try to parse as a plain number (assume seconds)
    try:
        return timedelta(seconds=float(elapsed_str))
    except ValueError:
        pass

    raise ValueError(f"Invalid elapsed time format: {elapsed_str}")


def parse_date(date_str: str, fmt: str = "YYYYMMDD") -> datetime:
    """Parse date string to datetime in configured timezone.

    Args:
    ----
        date_str: Date string (e.g., "20240101")
        fmt: Format string in pendulum format (default: "YYYYMMDD")

    Returns:
    -------
        datetime: Parsed datetime in configured timezone

    """
    tz = get_timezone()
    parsed = pendulum.from_format(date_str, fmt, tz=tz)
    return datetime(
        parsed.year,
        parsed.month,
        parsed.day,
        parsed.hour,
        parsed.minute,
        parsed.second,
        parsed.microsecond,
        tzinfo=parsed.tzinfo,
    )


def start_of_day(dt: datetime) -> datetime:
    """Get the start of day for a datetime.

    Args:
    ----
        dt: datetime object

    Returns:
    -------
        datetime: Start of day (00:00:00)

    """
    pdt = pendulum.instance(dt)
    start = pdt.start_of("day")
    return datetime(
        start.year,
        start.month,
        start.day,
        start.hour,
        start.minute,
        start.second,
        start.microsecond,
        tzinfo=start.tzinfo,
    )


def end_of_day(dt: datetime) -> datetime:
    """Get the end of day for a datetime.

    Args:
    ----
        dt: datetime object

    Returns:
    -------
        datetime: End of day (23:59:59.999999)

    """
    pdt = pendulum.instance(dt)
    end = pdt.end_of("day")
    return datetime(
        end.year,
        end.month,
        end.day,
        end.hour,
        end.minute,
        end.second,
        end.microsecond,
        tzinfo=end.tzinfo,
    )
