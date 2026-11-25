"""The Execution list grouped by agent session, and one session's graph over its executions.

Both are read-only projections of records that already exist. Nothing here creates, schedules,
locks, or cancels an execution, and no record is changed to make a group: a session row is the
session record plus the real executions its actions dispatched (see ``agent_execution_links``),
and the graph adds the session's decisions and interventions as typed nodes and edges.

Statuses keep their owners. A group's status is the session's (``active``, ``waiting_for_human``,
``completed``, ``cancelled``, ``expired``); each child is its own execution's. A session holds no
hardware lock between measurements or while it waits for a person, and is not failed for it.

This module is the service the router depends on. The work lives in focused modules:

- ``execution_group_list``: which rows exist, their order, and the page cut;
- ``execution_group_rows``: the rows of one cut page, assembled with batched reads;
- ``agent_session_graph``: one session's graph;
- ``agent_session_group_summary``: the agent session header both views share.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.api.services.agent_session_graph import (
    MAX_SESSION_GRAPH_NODES,
    MAX_TEXT,
    SESSION_GRAPH_NOTES,
    build_session_graph,
)
from qdash.api.services.agent_session_group_summary import (
    MAX_MISSING,
    UNANSWERED_INTERVENTION_STATUSES,
)
from qdash.api.services.execution_group_list import list_execution_groups
from qdash.api.services.execution_group_rows import (
    MAX_LIST_AGENT_SESSIONS,
    MAX_LIST_CHILDREN,
    MAX_LIST_RUNS,
    run_target_qids,
)

if TYPE_CHECKING:
    from qdash.api.schemas.execution_group import (
        AgentSessionGraphResponse,
        ListExecutionGroupsResponse,
    )
    from qdash.repository.execution_history import MongoExecutionHistoryRepository

__all__ = [
    "MAX_LIST_AGENT_SESSIONS",
    "MAX_LIST_CHILDREN",
    "MAX_LIST_RUNS",
    "MAX_MISSING",
    "MAX_SESSION_GRAPH_NODES",
    "MAX_TEXT",
    "SESSION_GRAPH_NOTES",
    "UNANSWERED_INTERVENTION_STATUSES",
    "ExecutionGroupService",
    "run_target_qids",
]


class ExecutionGroupService:
    """Read the Execution list grouped by agent session, and one session's graph."""

    def __init__(self, execution_history_repository: MongoExecutionHistoryRepository) -> None:
        self._history_repo = execution_history_repository

    def list_groups(
        self,
        *,
        project_id: str,
        chip_id: str,
        skip: int = 0,
        limit: int = 20,
        date: str | None = None,
        timezone: str = "UTC",
    ) -> ListExecutionGroupsResponse:
        """A page of rows, newest first: calibration sessions, agent sessions, and executions.

        Rows are grouped before the page is cut; see ``list_execution_groups``.
        """
        return list_execution_groups(
            project_id=project_id,
            chip_id=chip_id,
            skip=skip,
            limit=limit,
            date=date,
            timezone=timezone,
        )

    def get_session_graph(self, *, project_id: str, session_id: str) -> AgentSessionGraphResponse:
        """The session's measurements, proposals, decisions, and interventions as a graph.

        The session is read in the caller's project only; see ``build_session_graph``.
        """
        return build_session_graph(project_id=project_id, session_id=session_id)
