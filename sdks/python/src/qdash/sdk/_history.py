"""Listing past executions and task results for investigation, one page per request.

``QDash.executions.list(chip_id=...)`` and ``QDash.task_results.list(...)`` read one page of
summary rows. A page holds only the rows of its own request: iterating it, ``len()``,
:meth:`~_Page.to_records` and :meth:`~_Page.to_dataframe` send nothing, and only
:meth:`~_Page.next_page` reads the following page, with the same filters. To read one row in
full, use ``QDash.execution(row.execution_id).get()`` or ``QDash.task_result(row.task_id)``.
"""

from __future__ import annotations

import datetime as dt
import re
import zoneinfo
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from qdash.sdk._http import api_errors, given, read_options

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import pandas

    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.types.execution_response_summary import ExecutionResponseSummary
    from qdash.sdk._generated.types.task_result_list_item import TaskResultListItem

_DASHED_DAY = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
_COMPACT_DAY = re.compile(r"\d{8}", re.ASCII)

# The server's page size bound for both list routes.
MAX_LIMIT = 100

EXECUTION_COLUMNS: tuple[str, ...] = (
    "execution_id",
    "name",
    "status",
    "start_at",
    "end_at",
    "elapsed_time",
    "username",
    "message",
)
TASK_RESULT_COLUMNS: tuple[str, ...] = (
    "task_id",
    "execution_id",
    "chip_id",
    "task_name",
    "qid",
    "status",
    "start_at",
    "end_at",
    "elapsed_time",
    "username",
    "message",
    "step_id",
    "call_id",
)

RowT = TypeVar("RowT")
PageT = TypeVar("PageT", bound="_Page[Any]")


def _check_int(name: str, value: object, *, low: int, high: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, not {type(value).__name__}")
    if value < low or (high is not None and value > high):
        bound = f"between {low} and {high}" if high is not None else f"at least {low}"
        raise ValueError(f"{name} must be {bound}, got {value}")
    return value


def _check_paging(skip: object, limit: object) -> tuple[int, int]:
    return _check_int("skip", skip, low=0), _check_int("limit", limit, low=1, high=MAX_LIMIT)


def _check_text(name: str, value: object) -> str | None:
    """A string filter: None leaves it out; an empty string is refused, not sent as no filter."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, not {type(value).__name__}")
    if not value:
        raise ValueError(f"{name} must be a non-empty string; pass None to leave it out")
    return value


def _day(value: object) -> str:
    """``value`` as the server's ``YYYYMMDD`` day."""
    if isinstance(value, dt.datetime):
        raise TypeError("date must be a calendar day; pass value.date() or a YYYY-MM-DD string")
    if isinstance(value, dt.date):
        return value.strftime("%Y%m%d")
    if not isinstance(value, str):
        raise TypeError(f"date must be a datetime.date or a string, not {type(value).__name__}")
    digits = value.replace("-", "") if _DASHED_DAY.fullmatch(value) else value
    try:
        if not _COMPACT_DAY.fullmatch(digits):
            raise ValueError
        return dt.datetime.strptime(digits, "%Y%m%d").date().strftime("%Y%m%d")
    except ValueError:
        raise ValueError(
            f"date must be a valid YYYY-MM-DD or YYYYMMDD day, got {value!r}"
        ) from None


def _zone(value: object) -> str:
    """An IANA zone name, checked locally when this machine has a time zone database."""
    if not isinstance(value, str) or not value:
        raise ValueError("timezone must be a non-empty IANA time zone name, such as 'Asia/Tokyo'")
    try:
        zoneinfo.ZoneInfo(value)
    except zoneinfo.ZoneInfoNotFoundError:
        # Without a local database the server, which resolves the zone, decides.
        if zoneinfo.available_timezones():
            raise ValueError(f"unknown IANA time zone {value!r}") from None
    except ValueError:
        raise ValueError(f"unknown IANA time zone {value!r}") from None
    return value


def _instant(name: str, value: object) -> dt.datetime | None:
    if value is None:
        return None
    if not isinstance(value, dt.datetime):
        raise TypeError(f"{name} must be a timezone-aware datetime.datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{name} has no time zone, so the instant it names is ambiguous; pass an aware "
            "datetime, such as datetime(2026, 11, 24, tzinfo=ZoneInfo('Asia/Tokyo'))"
        )
    return value


def _has_next(skip: int, count: int, limit: int, total: int | None) -> bool | None:
    """Whether rows follow this page; None when the server reported no total to tell by."""
    if count == 0:
        return False
    if total is not None:
        return skip + count < total
    if count < limit:
        return False
    return None


class _Page(Generic[RowT]):
    """One page of summary rows, as one request returned them; reading it sends nothing."""

    _columns: tuple[str, ...] = ()

    def __init__(
        self,
        items: list[RowT],
        *,
        total: int | None,
        skip: int,
        limit: int,
        fetch: Callable[[int], Any],
    ) -> None:
        self.items = items
        self.total = total
        self.skip = skip
        self.limit = limit
        self._fetch = fetch

    @property
    def has_next(self) -> bool | None:
        """Whether a next page has rows; None when unknown (no total, and a full page)."""
        return _has_next(self.skip, len(self.items), self.limit, self.total)

    def next_page(self: PageT) -> PageT | None:
        """The page after this one, with the same filters and limit; one request, or None.

        Returns None without a request when :attr:`has_next` is false. The next page starts
        after the rows this page returned. An empty page always ends paging; a short page
        ends paging when the total is unknown.
        """
        if self.has_next is False:
            return None
        page: PageT = self._fetch(self.skip + len(self.items))
        return page

    def __iter__(self) -> Iterator[RowT]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> RowT:
        return self.items[index]

    def _record(self, row: RowT) -> dict[str, Any]:
        raise NotImplementedError

    def to_records(self) -> list[dict[str, Any]]:
        """This page's rows as flat dicts with fixed keys; ``items`` keep every field."""
        return [self._record(row) for row in self.items]

    def to_dataframe(self) -> pandas.DataFrame:
        """This page's :meth:`to_records` as a pandas DataFrame, with the same columns when empty.

        Needs pandas, which the SDK does not install. Times stay datetimes, and missing values
        are None or NaT.
        """
        try:
            import pandas
        except ImportError:
            raise ImportError(
                "to_dataframe() needs pandas; install it with `pip install pandas`, or use "
                "to_records() instead"
            ) from None
        return pandas.DataFrame.from_records(self.to_records(), columns=list(self._columns))

    def _summary(self) -> str:
        return (
            f"rows={len(self.items)}, skip={self.skip}, limit={self.limit}, "
            f"total={self.total}, has_next={self.has_next}"
        )


class ExecutionPage(_Page["ExecutionResponseSummary"]):
    """One page of a chip's executions, newest first, as ``QDash.executions.list`` read it.

    ``items`` are the API's execution summaries with every field. ``total`` is the number of
    executions that match, or None when the server did not report one.
    """

    _columns = EXECUTION_COLUMNS

    def __init__(
        self,
        items: list[ExecutionResponseSummary],
        *,
        chip_id: str,
        total: int | None,
        skip: int,
        limit: int,
        fetch: Callable[[int], ExecutionPage],
    ) -> None:
        super().__init__(items, total=total, skip=skip, limit=limit, fetch=fetch)
        self.chip_id = chip_id

    def _record(self, row: ExecutionResponseSummary) -> dict[str, Any]:
        return {
            "execution_id": row.execution_id,
            "name": row.name,
            "status": row.status,
            "start_at": row.start_at,
            "end_at": row.end_at,
            "elapsed_time": row.elapsed_time,
            "username": row.username,
            "message": row.message,
        }

    def __repr__(self) -> str:
        return f"ExecutionPage(chip_id={self.chip_id!r}, {self._summary()})"


class TaskResultPage(_Page["TaskResultListItem"]):
    """One page of task results, newest first, as ``QDash.task_results.list`` read it.

    ``items`` are the API's task result rows with every field. ``status_counts`` is the
    server's count of results per status, as it returned it: it counts every result that
    matches the other filters, whatever the ``status`` filter, across all pages.
    """

    _columns = TASK_RESULT_COLUMNS

    def __init__(
        self,
        items: list[TaskResultListItem],
        *,
        total: int,
        skip: int,
        limit: int,
        status_counts: dict[str, int],
        filters: dict[str, Any],
        fetch: Callable[[int], TaskResultPage],
    ) -> None:
        super().__init__(items, total=total, skip=skip, limit=limit, fetch=fetch)
        self.status_counts = status_counts
        self.filters = filters

    def _record(self, row: TaskResultListItem) -> dict[str, Any]:
        invocation = row.invocation
        return {
            "task_id": row.task_id,
            "execution_id": row.execution_id,
            "chip_id": row.chip_id,
            "task_name": row.task_name,
            "qid": row.qid,
            "status": row.status,
            "start_at": row.start_at,
            "end_at": row.end_at,
            "elapsed_time": row.elapsed_time,
            "username": row.username,
            "message": row.message,
            "step_id": invocation.step_id if invocation is not None else None,
            "call_id": invocation.call_id if invocation is not None else None,
        }

    def __repr__(self) -> str:
        return f"TaskResultPage({self._summary()}, filters={self.filters!r})"


class ExecutionHistory:
    """Past executions of the session's project, reached as ``QDash.executions``."""

    def __init__(self, api: QDashApi, config: QDashConfig) -> None:
        self._api = api
        self._config = config

    def list(
        self,
        *,
        chip_id: str,
        date: dt.date | str | None = None,
        timezone: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> ExecutionPage:
        """One page of ``chip_id``'s executions, newest first; sends one request.

        ``date`` (a ``datetime.date``, ``YYYY-MM-DD`` or ``YYYYMMDD``) keeps the executions
        started on that day in ``timezone``, an IANA name such as ``Asia/Tokyo``; without
        ``timezone`` the server uses UTC. ``limit`` is 1 to 100. Invalid arguments raise
        before any request.
        """
        if _check_text("chip_id", chip_id) is None:
            raise ValueError("chip_id must be a non-empty string")
        skip, limit = _check_paging(skip, limit)
        day = _day(date) if date is not None else None
        if timezone is not None:
            if day is None:
                raise ValueError("timezone only applies with date; pass a date too")
            timezone = _zone(timezone)
        return self._page(chip_id, day, timezone, skip, limit)

    def _page(
        self, chip_id: str, day: str | None, timezone: str | None, skip: int, limit: int
    ) -> ExecutionPage:
        with api_errors():
            response = self._api.execution.list_executions(
                chip_id=chip_id,
                skip=skip,
                limit=limit,
                **given(date=day, timezone=timezone),
                request_options=read_options(self._config),
            )
        return ExecutionPage(
            list(response.executions),
            chip_id=chip_id,
            total=response.total,
            skip=skip,
            limit=limit,
            fetch=lambda offset: self._page(chip_id, day, timezone, offset, limit),
        )

    def __repr__(self) -> str:
        return "ExecutionHistory()"


class TaskResultHistory:
    """Saved task results of the session's project, reached as ``QDash.task_results``."""

    def __init__(self, api: QDashApi, config: QDashConfig) -> None:
        self._api = api
        self._config = config

    def list(
        self,
        *,
        chip_id: str | None = None,
        task_name: str | None = None,
        qid: str | None = None,
        execution_id: str | None = None,
        status: str | None = None,
        username: str | None = None,
        start_from: dt.datetime | None = None,
        start_to: dt.datetime | None = None,
        message_contains: str | None = None,
        step_id: str | None = None,
        call_id: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> TaskResultPage:
        """One page of task results that match every given filter, newest first; one request.

        Text filters match exactly, except ``message_contains``, a case-insensitive substring;
        ``status`` is sent as given. ``start_from`` and ``start_to`` bound the start time,
        inclusively, and must be timezone-aware datetimes. ``limit`` is 1 to 100. Invalid
        arguments raise before any request.
        """
        filters: dict[str, Any] = {
            name: _check_text(name, value)
            for name, value in (
                ("chip_id", chip_id),
                ("task_name", task_name),
                ("qid", qid),
                ("execution_id", execution_id),
                ("status", status),
                ("username", username),
                ("message_contains", message_contains),
                ("step_id", step_id),
                ("call_id", call_id),
            )
        }
        lower = _instant("start_from", start_from)
        upper = _instant("start_to", start_to)
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("start_from must not be later than start_to")
        filters["start_from"] = lower
        filters["start_to"] = upper
        skip, limit = _check_paging(skip, limit)
        return self._page(given(**filters), skip, limit)

    def _page(self, filters: dict[str, Any], skip: int, limit: int) -> TaskResultPage:
        with api_errors():
            response = self._api.task_result.list_task_results(
                **filters, skip=skip, limit=limit, request_options=read_options(self._config)
            )
        return TaskResultPage(
            list(response.items),
            total=response.total,
            skip=skip,
            limit=limit,
            status_counts=dict(response.status_counts),
            filters=dict(filters),
            fetch=lambda offset: self._page(filters, offset, limit),
        )

    def __repr__(self) -> str:
        return "TaskResultHistory()"
