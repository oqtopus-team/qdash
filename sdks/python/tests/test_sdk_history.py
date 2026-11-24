"""Investigation lists: QDash.executions.list and QDash.task_results.list, one page per request."""

from __future__ import annotations

import datetime as dt
import sys
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from test_sdk_session import Server

from qdash.sdk import (
    ExecutionHistory,
    ExecutionPage,
    QDashApiError,
    QDashAuthError,
    QDashNotFoundError,
    QDashValidationError,
    TaskResultHistory,
    TaskResultPage,
)
from qdash.sdk._history import EXECUTION_COLUMNS, TASK_RESULT_COLUMNS
from qdash.sdk.types import ExecutionResponseSummary, TaskResultListItem

EXECUTIONS = "/executions"
TASK_RESULTS = "/task-results"
TOKYO = ZoneInfo("Asia/Tokyo")


def execution_row(execution_id: str = "exec-1", **extra: Any) -> dict[str, Any]:
    return {
        "name": "full-calibration",
        "execution_id": execution_id,
        "status": "completed",
        "username": "alice",
        "start_at": "2026-11-24T01:00:00Z",
        "end_at": "2026-11-24T01:30:00Z",
        "elapsed_time": "0:30:00",
        "tags": ["daily"],
        "note": {"flow_run_id": "fr-1"},
        **extra,
    }


def executions_body(rows: list[dict[str, Any]], **meta: Any) -> dict[str, Any]:
    return {"executions": rows, **meta}


def task_row(task_id: str = "task-1", **extra: Any) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "task_name": "CheckT1",
        "qid": "0",
        "chip_id": "64Qv3",
        "status": "failed",
        "execution_id": "exec-1",
        "username": "alice",
        "message": "fit did not converge",
        "has_stack_trace": True,
        "start_at": "2026-11-24T01:00:00Z",
        "end_at": "2026-11-24T01:01:00Z",
        "elapsed_time": "0:01:00",
        **extra,
    }


def tasks_body(
    rows: list[dict[str, Any]], *, total: int, skip: int = 0, limit: int = 50, **counts: int
) -> dict[str, Any]:
    return {
        "items": rows,
        "total": total,
        "skip": skip,
        "limit": limit,
        "status_counts": counts or {"completed": 3, "failed": 1},
    }


def params(server: Server, index: int = -1) -> dict[str, str]:
    return dict(server.requests[index].url.params)


# Executions


def test_executions_list_sends_the_chip_and_default_paging_only() -> None:
    server = Server(
        {
            ("GET", EXECUTIONS): [
                httpx.Response(
                    200,
                    json=executions_body(
                        [execution_row(extra="kept"), execution_row("exec-2")],
                        total=2,
                        skip=0,
                        limit=20,
                    ),
                )
            ]
        }
    )
    with server.session(project_id="project-b") as qdash:
        assert isinstance(qdash.executions, ExecutionHistory)
        page = qdash.executions.list(chip_id="64Qv3")

    assert isinstance(page, ExecutionPage)
    assert params(server) == {"chip_id": "64Qv3", "skip": "0", "limit": "20"}
    assert server.requests[0].headers["X-Project-Id"] == "project-b"
    assert all(isinstance(row, ExecutionResponseSummary) for row in page.items)
    assert [row.execution_id for row in page] == ["exec-1", "exec-2"]
    assert page.items[0].model_extra == {"extra": "kept"}
    assert page.items[0].tags == ["daily"]
    assert (page.chip_id, page.total, page.skip, page.limit) == ("64Qv3", 2, 0, 20)
    assert len(page) == 2
    assert page[1].execution_id == "exec-2"
    assert page.has_next is False


@pytest.mark.parametrize("day", [dt.date(2026, 11, 4), "2026-11-04", "20261104"])
def test_executions_list_normalizes_the_day_and_passes_the_zone(day: Any) -> None:
    server = Server({("GET", EXECUTIONS): [httpx.Response(200, json=executions_body([]))]})
    server.session().executions.list(
        chip_id="64Qv3", date=day, timezone="Asia/Tokyo", skip=40, limit=100
    )

    assert params(server) == {
        "chip_id": "64Qv3",
        "date": "20261104",
        "timezone": "Asia/Tokyo",
        "skip": "40",
        "limit": "100",
    }


def test_executions_list_leaves_the_zone_to_the_server_when_not_given() -> None:
    server = Server({("GET", EXECUTIONS): [httpx.Response(200, json=executions_body([]))]})
    server.session().executions.list(chip_id="64Qv3", date="2026-11-04")

    assert "timezone" not in params(server)
    assert params(server)["date"] == "20261104"


@pytest.mark.parametrize(
    ("kwargs", "error", "match"),
    [
        ({"chip_id": ""}, ValueError, "chip_id"),
        ({"chip_id": None}, ValueError, "chip_id"),
        ({"chip_id": 3}, TypeError, "chip_id"),
        ({"chip_id": "c", "skip": -1}, ValueError, "skip"),
        ({"chip_id": "c", "skip": True}, TypeError, "skip"),
        ({"chip_id": "c", "skip": 1.0}, TypeError, "skip"),
        ({"chip_id": "c", "limit": 0}, ValueError, "limit"),
        ({"chip_id": "c", "limit": 101}, ValueError, "limit"),
        ({"chip_id": "c", "limit": False}, TypeError, "limit"),
        ({"chip_id": "c", "date": "2026-02-30"}, ValueError, "date"),
        ({"chip_id": "c", "date": "2026/11/04"}, ValueError, "date"),
        ({"chip_id": "c", "date": "yesterday"}, ValueError, "date"),
        ({"chip_id": "c", "date": "2026114"}, ValueError, "date"),
        ({"chip_id": "c", "date": "2026-1-4"}, ValueError, "date"),
        ({"chip_id": "c", "date": "2026-1104"}, ValueError, "date"),
        ({"chip_id": "c", "date": 20261104}, TypeError, "date"),
        ({"chip_id": "c", "date": dt.datetime(2026, 11, 4, tzinfo=TOKYO)}, TypeError, "date"),
        ({"chip_id": "c", "date": "2026-11-04", "timezone": "Mars/Olympus"}, ValueError, "zone"),
        ({"chip_id": "c", "date": "2026-11-04", "timezone": ""}, ValueError, "zone"),
        ({"chip_id": "c", "timezone": "Asia/Tokyo"}, ValueError, "timezone only applies"),
    ],
)
def test_executions_list_rejects_invalid_arguments_before_a_request(
    kwargs: dict[str, Any], error: type[Exception], match: str
) -> None:
    server = Server()
    with pytest.raises(error, match=match):
        server.session().executions.list(**kwargs)
    assert server.requests == []


def test_executions_next_page_keeps_filters_and_advances_by_the_rows_returned() -> None:
    server = Server(
        {
            ("GET", EXECUTIONS): [
                httpx.Response(
                    200,
                    json=executions_body(
                        [execution_row("a"), execution_row("b")], total=3, skip=0, limit=2
                    ),
                ),
                httpx.Response(
                    200, json=executions_body([execution_row("c")], total=3, skip=2, limit=2)
                ),
            ]
        }
    )
    first = server.session().executions.list(
        chip_id="64Qv3", date="20261104", timezone="Asia/Tokyo", limit=2
    )
    assert first.has_next is True
    assert len(server.requests) == 1

    second = first.next_page()
    assert isinstance(second, ExecutionPage)
    assert [row.execution_id for row in second] == ["c"]
    assert params(server) == {
        "chip_id": "64Qv3",
        "date": "20261104",
        "timezone": "Asia/Tokyo",
        "skip": "2",
        "limit": "2",
    }
    assert second.has_next is False
    assert second.next_page() is None
    assert len(server.requests) == 2


def test_executions_without_a_total_page_until_an_empty_or_short_page() -> None:
    server = Server(
        {
            ("GET", EXECUTIONS): [
                httpx.Response(200, json=executions_body([execution_row("a"), execution_row("b")])),
                httpx.Response(200, json=executions_body([execution_row("c")])),
            ]
        }
    )
    first = server.session().executions.list(chip_id="64Qv3", limit=2)
    assert first.total is None
    assert first.has_next is None  # a full page without a total: more rows may follow

    second = first.next_page()
    assert second is not None
    assert params(server)["skip"] == "2"
    assert second.has_next is False  # short page
    assert second.next_page() is None
    assert len(server.requests) == 2


def test_an_empty_page_ends_paging_even_when_the_total_says_otherwise() -> None:
    server = Server(
        {("GET", EXECUTIONS): [httpx.Response(200, json=executions_body([], total=10, skip=4))]}
    )
    page = server.session().executions.list(chip_id="64Qv3", skip=4)

    assert page.has_next is False
    assert page.next_page() is None
    assert len(server.requests) == 1


def test_execution_records_and_iteration_send_nothing() -> None:
    server = Server(
        {
            ("GET", EXECUTIONS): [
                httpx.Response(
                    200,
                    json=executions_body(
                        [execution_row(message="ok"), execution_row("exec-2", start_at=None)],
                        total=40,
                    ),
                )
            ]
        }
    )
    page = server.session().executions.list(chip_id="64Qv3", limit=2)
    records = page.to_records()
    list(page)
    repr(page)

    assert len(server.requests) == 1
    assert [tuple(record) for record in records] == [EXECUTION_COLUMNS] * 2
    assert records[0] == {
        "execution_id": "exec-1",
        "name": "full-calibration",
        "status": "completed",
        "start_at": dt.datetime(2026, 11, 24, 1, tzinfo=dt.UTC),
        "end_at": dt.datetime(2026, 11, 24, 1, 30, tzinfo=dt.UTC),
        "elapsed_time": "0:30:00",
        "username": "alice",
        "message": "ok",
    }
    assert records[1]["start_at"] is None
    assert repr(page) == (
        "ExecutionPage(chip_id='64Qv3', rows=2, skip=0, limit=2, total=40, has_next=True)"
    )


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, QDashApiError),
        (401, QDashAuthError),
        (404, QDashNotFoundError),
        (422, QDashValidationError),
    ],
)
def test_executions_errors_are_translated(status: int, error: type[QDashApiError]) -> None:
    server = Server({("GET", EXECUTIONS): [httpx.Response(status, json={"detail": "nope"})]})
    with pytest.raises(error, match="nope") as raised:
        server.session().executions.list(chip_id="64Qv3")
    assert raised.value.status_code == status


def test_list_reads_retry_transient_statuses() -> None:
    server = Server(
        {
            ("GET", EXECUTIONS): [
                httpx.Response(503, headers={"retry-after-ms": "1"}),
                httpx.Response(200, json=executions_body([execution_row()], total=1)),
            ],
            ("GET", TASK_RESULTS): [
                httpx.Response(503, headers={"retry-after-ms": "1"}),
                httpx.Response(200, json=tasks_body([task_row()], total=1)),
            ],
        }
    )
    qdash = server.session()
    assert len(qdash.executions.list(chip_id="64Qv3")) == 1
    assert len(qdash.task_results.list()) == 1
    assert len(server.requests) == 4


def test_with_project_scopes_both_lists() -> None:
    server = Server(
        {
            ("GET", EXECUTIONS): [httpx.Response(200, json=executions_body([]))],
            ("GET", TASK_RESULTS): [httpx.Response(200, json=tasks_body([], total=0))],
        }
    )
    scoped = server.session().with_project("project-z")
    scoped.executions.list(chip_id="64Qv3")
    scoped.task_results.list()

    assert [request.headers["X-Project-Id"] for request in server.requests] == ["project-z"] * 2


# Task results


def test_task_results_list_sends_default_paging_only() -> None:
    server = Server({("GET", TASK_RESULTS): [httpx.Response(200, json=tasks_body([], total=0))]})
    with server.session() as qdash:
        assert isinstance(qdash.task_results, TaskResultHistory)
        page = qdash.task_results.list()

    assert isinstance(page, TaskResultPage)
    assert params(server) == {"skip": "0", "limit": "50"}
    assert server.requests[0].headers["X-Project-Id"] == "project-a"
    assert page.filters == {}


def test_task_results_list_maps_every_filter() -> None:
    server = Server({("GET", TASK_RESULTS): [httpx.Response(200, json=tasks_body([], total=0))]})
    server.session().task_results.list(
        chip_id="64Qv3",
        task_name="CheckT1",
        qid="0-1",
        execution_id="exec-1",
        status="failed",
        username="alice",
        start_from=dt.datetime(2026, 11, 24, 9, tzinfo=TOKYO),
        start_to=dt.datetime(2026, 11, 24, 12, tzinfo=dt.UTC),
        message_contains="did not converge",
        step_id="coarse",
        call_id="t1-fine",
        skip=100,
        limit=25,
    )

    assert params(server) == {
        "chip_id": "64Qv3",
        "task_name": "CheckT1",
        "qid": "0-1",
        "execution_id": "exec-1",
        "status": "failed",
        "username": "alice",
        "start_from": "2026-11-24T09:00:00+09:00",
        "start_to": "2026-11-24T12:00:00Z",
        "message_contains": "did not converge",
        "step_id": "coarse",
        "call_id": "t1-fine",
        "skip": "100",
        "limit": "25",
    }


@pytest.mark.parametrize(
    ("kwargs", "error", "match"),
    [
        ({"start_from": dt.datetime(2026, 11, 24, 9)}, ValueError, "no time zone"),
        ({"start_to": dt.datetime(2026, 11, 24, 9)}, ValueError, "no time zone"),
        ({"start_from": dt.date(2026, 11, 24)}, TypeError, "start_from"),
        ({"start_from": "2026-11-24T00:00:00Z"}, TypeError, "start_from"),
        (
            {
                "start_from": dt.datetime(2026, 11, 24, 12, tzinfo=dt.UTC),
                "start_to": dt.datetime(2026, 11, 24, 9, tzinfo=dt.UTC),
            },
            ValueError,
            "later than",
        ),
        ({"chip_id": ""}, ValueError, "chip_id"),
        ({"status": ""}, ValueError, "status"),
        ({"qid": 0}, TypeError, "qid"),
        ({"skip": -1}, ValueError, "skip"),
        ({"limit": 101}, ValueError, "limit"),
        ({"limit": True}, TypeError, "limit"),
    ],
)
def test_task_results_list_rejects_invalid_arguments_before_a_request(
    kwargs: dict[str, Any], error: type[Exception], match: str
) -> None:
    server = Server()
    with pytest.raises(error, match=match):
        server.session().task_results.list(**kwargs)
    assert server.requests == []


def test_an_equal_start_range_is_accepted() -> None:
    server = Server({("GET", TASK_RESULTS): [httpx.Response(200, json=tasks_body([], total=0))]})
    moment = dt.datetime(2026, 11, 24, 9, tzinfo=dt.UTC)
    server.session().task_results.list(start_from=moment, start_to=moment)
    assert len(server.requests) == 1


def test_task_results_page_keeps_rows_counts_and_paging() -> None:
    server = Server(
        {
            ("GET", TASK_RESULTS): [
                httpx.Response(
                    200,
                    json=tasks_body(
                        [task_row(extra="kept"), task_row("task-2")],
                        total=5,
                        limit=2,
                        completed=4,
                        failed=1,
                    ),
                ),
                httpx.Response(
                    200, json=tasks_body([task_row("task-3")], total=5, skip=2, limit=2, failed=1)
                ),
            ]
        }
    )
    page = server.session().task_results.list(chip_id="64Qv3", status="failed", limit=2)

    assert all(isinstance(row, TaskResultListItem) for row in page.items)
    assert page.items[0].model_extra == {"extra": "kept"}
    assert page.items[0].has_stack_trace is True
    assert page.status_counts == {"completed": 4, "failed": 1}
    assert (page.total, page.skip, page.limit, page.has_next) == (5, 0, 2, True)
    assert repr(page) == (
        "TaskResultPage(rows=2, skip=0, limit=2, total=5, has_next=True, "
        "filters={'chip_id': '64Qv3', 'status': 'failed'})"
    )
    assert len(server.requests) == 1

    second = page.next_page()
    assert isinstance(second, TaskResultPage)
    assert params(server) == {"chip_id": "64Qv3", "status": "failed", "skip": "2", "limit": "2"}
    assert [row.task_id for row in second] == ["task-3"]
    assert second.has_next is True  # 3 of 5 read
    assert second.filters == page.filters


def test_task_records_flatten_the_invocation_when_present() -> None:
    server = Server(
        {
            ("GET", TASK_RESULTS): [
                httpx.Response(
                    200,
                    json=tasks_body(
                        [
                            task_row(
                                invocation={
                                    "step_id": "coarse",
                                    "call_id": "t1",
                                    "settings": {"run": {"shots": 1024}},
                                }
                            ),
                            task_row("task-2", invocation={"call_id": "t1"}),
                            task_row("task-3", message=None, start_at=None),
                        ],
                        total=3,
                    ),
                )
            ]
        }
    )
    page = server.session().task_results.list()
    records = page.to_records()

    assert len(server.requests) == 1
    assert [tuple(record) for record in records] == [TASK_RESULT_COLUMNS] * 3
    assert records[0] == {
        "task_id": "task-1",
        "execution_id": "exec-1",
        "chip_id": "64Qv3",
        "task_name": "CheckT1",
        "qid": "0",
        "status": "failed",
        "start_at": dt.datetime(2026, 11, 24, 1, tzinfo=dt.UTC),
        "end_at": dt.datetime(2026, 11, 24, 1, 1, tzinfo=dt.UTC),
        "elapsed_time": "0:01:00",
        "username": "alice",
        "message": "fit did not converge",
        "step_id": "coarse",
        "call_id": "t1",
    }
    assert (records[1]["step_id"], records[1]["call_id"]) == (None, "t1")
    assert (records[2]["step_id"], records[2]["call_id"]) == (None, None)
    assert (records[2]["message"], records[2]["start_at"]) == (None, None)
    # The full row keeps what the records leave out.
    assert page.items[0].invocation is not None
    assert page.items[0].invocation.settings == {"run": {"shots": 1024}}


def test_detail_drilldown_uses_the_existing_handles() -> None:
    server = Server(
        {("GET", TASK_RESULTS): [httpx.Response(200, json=tasks_body([task_row()], total=1))]}
    )
    qdash = server.session()
    row = qdash.task_results.list()[0]
    assert qdash.execution(row.execution_id).execution_id == "exec-1"
    assert len(server.requests) == 1


# DataFrames


def test_to_dataframe_has_stable_columns_even_when_empty() -> None:
    pandas = pytest.importorskip("pandas")
    server = Server(
        {
            ("GET", EXECUTIONS): [httpx.Response(200, json=executions_body([]))],
            ("GET", TASK_RESULTS): [httpx.Response(200, json=tasks_body([], total=0))],
        }
    )
    qdash = server.session()
    executions = qdash.executions.list(chip_id="64Qv3").to_dataframe()
    tasks = qdash.task_results.list().to_dataframe()

    assert isinstance(executions, pandas.DataFrame)
    assert list(executions.columns) == list(EXECUTION_COLUMNS)
    assert list(tasks.columns) == list(TASK_RESULT_COLUMNS)
    assert len(executions) == len(tasks) == 0
    assert len(server.requests) == 2


def test_to_dataframe_holds_the_current_page_only() -> None:
    pandas = pytest.importorskip("pandas")
    server = Server(
        {
            ("GET", TASK_RESULTS): [
                httpx.Response(
                    200,
                    json=tasks_body(
                        [task_row(invocation={"call_id": "t1"}), task_row("task-2", end_at=None)],
                        total=200,
                        limit=2,
                    ),
                )
            ]
        }
    )
    frame = server.session().task_results.list(limit=2).to_dataframe()

    assert len(server.requests) == 1
    assert list(frame.columns) == list(TASK_RESULT_COLUMNS)
    assert list(frame["task_id"]) == ["task-1", "task-2"]
    assert frame.loc[0, "start_at"] == pandas.Timestamp("2026-11-24T01:00:00Z")
    assert pandas.isna(frame.loc[1, "end_at"])
    assert frame.loc[0, "call_id"] == "t1"
    assert frame.loc[1, "call_id"] is None


def test_to_dataframe_without_pandas_says_how_to_install_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server({("GET", EXECUTIONS): [httpx.Response(200, json=executions_body([]))]})
    page = server.session().executions.list(chip_id="64Qv3")
    monkeypatch.setitem(sys.modules, "pandas", None)

    with pytest.raises(ImportError, match="pip install pandas"):
        page.to_dataframe()
    assert page.to_records() == []
