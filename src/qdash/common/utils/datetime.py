"""Datetime utilities for QDash application."""

from datetime import UTC, datetime, timedelta
from functools import lru_cache

import pendulum
from pendulum import DateTime as PendulumDateTime

DEFAULT_TIMEZONE = "Asia/Tokyo"
MAX_ELAPSED_TIME_STRING_LENGTH = 100
MAX_ELAPSED_TIME_SECONDS = 365 * 24 * 3600


@lru_cache(maxsize=1)
def get_timezone() -> str:
    """Get the configured timezone."""
    try:
        from qdash.config import get_settings

        return getattr(get_settings(), "timezone", DEFAULT_TIMEZONE)
    except Exception:
        return DEFAULT_TIMEZONE


def now() -> datetime:
    """Get current datetime in UTC."""
    return datetime.now(UTC)


def local_now() -> datetime:
    """Get current datetime in the configured display/calendar timezone."""
    pdt = pendulum.now(get_timezone())
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
    """Get current datetime as ISO8601 string."""
    return now().isoformat()


def ensure_timezone(value: datetime | None) -> datetime | None:
    """Ensure datetime is timezone-aware."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
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

    from datetime import timezone as dt_timezone

    return value.replace(tzinfo=dt_timezone.utc)


def to_datetime(value: str | datetime | PendulumDateTime | None) -> datetime | None:
    """Convert various datetime representations to datetime object."""
    if value is None:
        return None
    if isinstance(value, PendulumDateTime):
        return ensure_timezone(
            datetime(
                value.year,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
                value.microsecond,
                tzinfo=value.tzinfo,
            )
        )
    if isinstance(value, datetime):
        return ensure_timezone(value)
    if isinstance(value, str):
        parsed = pendulum.parse(value)
        if isinstance(parsed, PendulumDateTime):
            return ensure_timezone(
                datetime(
                    parsed.year,
                    parsed.month,
                    parsed.day,
                    parsed.hour,
                    parsed.minute,
                    parsed.second,
                    parsed.microsecond,
                    tzinfo=parsed.tzinfo,
                )
            )
        raise ValueError(f"Cannot parse datetime string: {value}")
    raise TypeError(f"Unsupported type for datetime conversion: {type(value)}")


def to_pendulum(value: str | datetime | PendulumDateTime | None) -> PendulumDateTime | None:
    """Convert various datetime representations to pendulum DateTime."""
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
    """Format datetime as ISO8601 string."""
    if dt is None:
        return None
    normalized = ensure_timezone(dt)
    if normalized is None:
        return None
    return normalized.isoformat()


def calculate_elapsed_time(start: datetime, end: datetime) -> timedelta:
    """Calculate elapsed time between two datetimes."""
    tz = get_timezone()
    start_p = pendulum.instance(start) if start.tzinfo else pendulum.instance(start, tz=tz)
    end_p = pendulum.instance(end) if end.tzinfo else pendulum.instance(end, tz=tz)
    diff = end_p.diff(start_p)
    return timedelta(seconds=diff.in_seconds())


def format_elapsed_time(elapsed: timedelta) -> str:
    """Format elapsed time as human-readable string."""
    total_seconds = int(elapsed.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def parse_elapsed_time(elapsed_str: str | timedelta | int | float | None) -> timedelta | None:
    """Parse elapsed time string to timedelta."""
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
    if len(elapsed_str) > MAX_ELAPSED_TIME_STRING_LENGTH:
        raise ValueError(
            f"Elapsed time string too long ({len(elapsed_str)} > {MAX_ELAPSED_TIME_STRING_LENGTH})"
        )

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

    total_seconds = 0.0
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

    lower_str = elapsed_str.lower()
    if "few second" in lower_str:
        return timedelta(seconds=5)
    if "second" in lower_str:
        return timedelta(seconds=1)
    if "minute" in lower_str:
        return timedelta(minutes=1)
    if "hour" in lower_str:
        return timedelta(hours=1)

    try:
        return timedelta(seconds=float(elapsed_str))
    except ValueError:
        pass

    raise ValueError(f"Invalid elapsed time format: {elapsed_str}")


def parse_date(date_str: str, fmt: str = "YYYYMMDD") -> datetime:
    """Parse date string to datetime in configured timezone."""
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
    """Get the start of day for a datetime."""
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
    """Get the end of day for a datetime."""
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
