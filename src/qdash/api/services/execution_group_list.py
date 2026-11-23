"""The grouped Execution list of one chip: which rows exist, their order, and the page cut.

Rows are grouped before the page is cut. Membership comes from the resolvers the rest of QDash
uses — ``agent_execution_links`` for the executions an agent session's actions hold, and
``calibration_session_groups`` for a calibration session's pipeline runs and admitted agent
sessions — so an execution is in at most one row. The rows of the cut page are assembled in
``execution_group_rows``. Nothing here writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bunnet import SortDirection

from qdash.api.schemas.execution_group import ListExecutionGroupsResponse
from qdash.api.services.agent_execution_links import resolve_chip_links, utc
from qdash.api.services.agent_session_group_summary import EPOCH
from qdash.api.services.calibration_session_groups import resolve_chip_calibration_groups
from qdash.api.services.execution_group_rows import MAX_LIST_CHILDREN, PageEntry, page_items
from qdash.api.services.execution_service import day_window
from qdash.dbmodel.execution_history import ExecutionHistoryDocument

if TYPE_CHECKING:
    from datetime import datetime


def list_execution_groups(
    *,
    project_id: str,
    chip_id: str,
    skip: int = 0,
    limit: int = 20,
    date: str | None = None,
    timezone: str = "UTC",
) -> ListExecutionGroupsResponse:
    """A page of rows, newest first: calibration sessions, agent sessions, and executions.

    Rows are grouped before the page is cut, so a session is one row with all of its
    executions. A calibration session row holds the step executions of its pipeline runs
    and its admitted agent sessions (each nested with its own executions); an agent session
    outside one is its own row; every other execution is its own row, ordered by its start
    as in the ungrouped list. A session row is ordered by its latest activity: its latest
    execution start, or its creation before the first. With ``date``, an execution row
    needs its start on that day and a session row its creation or an execution start on
    it; the row is then ordered by its latest activity of that day and still lists every
    execution.
    """
    window = day_window(date, timezone) if date else None
    links = resolve_chip_links(project_id, chip_id)
    calib = resolve_chip_calibration_groups(project_id, chip_id, links)

    def in_window(moment: datetime | None) -> bool:
        if window is None:
            return True
        return moment is not None and window[0] <= moment < window[1]

    def agent_moments(session_id: str) -> list[datetime]:
        return [links.session_created[session_id]] + [
            link.start_at
            for link in links.by_session.get(session_id, [])
            if link.start_at is not None
        ]

    rows: list[tuple[datetime, str, str]] = []
    for session_id in links.session_created:
        if session_id in calib.agent_parent:
            continue
        moments = [m for m in agent_moments(session_id) if in_window(m)]
        if moments:
            rows.append((max(moments), "agent_session", session_id))
    for cs_id, doc in calib.sessions.items():
        moments = [utc(doc.get("created_at")) or EPOCH]
        for run in calib.runs.get(cs_id, []):
            moments += [
                e.start_at
                for e in calib.run_executions.get(str(run["run_id"]), [])
                if e.start_at is not None
            ]
        for agent_id in calib.agents.get(cs_id, []):
            moments += agent_moments(agent_id)
        moments = [m for m in moments if in_window(m)]
        if moments:
            rows.append((max(moments), "calibration_session", cs_id))
    rows.sort(key=lambda row: (row[0], row[2]), reverse=True)

    grouped_ids = sorted(set(links.by_execution) | set(calib.execution_session))
    base = _chip_query(project_id, chip_id, window)
    collection = ExecutionHistoryDocument.get_motor_collection()
    total_executions = collection.count_documents(base)
    ungrouped = {**base, "execution_id": {"$nin": grouped_ids}}
    ungrouped_total = collection.count_documents(ungrouped)
    # The merged order needs at most skip + limit rows of each kind.
    heads = list(
        collection.find(ungrouped, {"_id": 0, "execution_id": 1, "start_at": 1})
        .sort([("start_at", SortDirection.DESCENDING), ("execution_id", SortDirection.DESCENDING)])
        .limit(skip + limit)
    )

    merged: list[PageEntry] = []
    i = j = 0
    while len(merged) < skip + limit and (i < len(rows) or j < len(heads)):
        row_at = rows[i][0] if i < len(rows) else None
        head_at = utc(heads[j].get("start_at")) if j < len(heads) else None
        take_row = i < len(rows) and (
            j >= len(heads) or head_at is None or (row_at or EPOCH) >= head_at
        )
        if take_row:
            merged.append((rows[i][1], rows[i][2], row_at))
            i += 1
        else:
            merged.append(("execution", str(heads[j]["execution_id"]), head_at))
            j += 1
    page = merged[skip : skip + limit]

    items = page_items(project_id, page, links, calib, in_window)
    agent_rows = sum(1 for row in rows if row[1] == "agent_session")
    return ListExecutionGroupsResponse(
        items=items,
        total=ungrouped_total + len(rows),
        total_executions=total_executions,
        grouped_executions=total_executions - ungrouped_total,
        agent_sessions=agent_rows,
        calibration_sessions=len(rows) - agent_rows,
        skip=skip,
        limit=limit,
        children_limit=MAX_LIST_CHILDREN,
    )


def _chip_query(
    project_id: str, chip_id: str, window: tuple[datetime, datetime] | None
) -> dict[str, Any]:
    query: dict[str, Any] = {"project_id": project_id, "chip_id": chip_id}
    if window is not None:
        query["start_at"] = {"$gte": window[0], "$lt": window[1]}
    return query
