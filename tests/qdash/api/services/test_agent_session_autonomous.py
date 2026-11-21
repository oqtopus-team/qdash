"""Server-side checks of autonomous steps in an agent session.

An autonomous step (pi-qdash's ``qdash_run_agent_session_step`` and
``qdash_request_agent_human``) runs without a per-call approval. QDash therefore checks,
with the request's authenticated user and its own records, that the signed-in user created
the ``auto`` session, and makes the history checks of a step one decision with its
state-version compare-and-set.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi import HTTPException

from qdash.api.schemas.agent_session import (
    CreateAgentInterventionRequest,
    CreateAgentSessionRequest,
    ExecuteAgentActionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.schemas.task_file import ListTaskInfoResponse, TaskInfo
from qdash.api.services.agent_session_gate import raw_document
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.datamodel.agent_session import (
    AgentActionType,
    AgentAutonomy,
    AgentInterventionReason,
    AgentSessionPolicy,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentActionDocument, AgentSessionDocument
from qdash.dbmodel.chip import ChipDocument

if TYPE_CHECKING:
    from qdash.api.schemas.agent_session import AgentSessionResponse
    from qdash.api.services.flow_service import FlowService
    from qdash.api.services.task_file_service import TaskFileService

PROJECT = "project-1"
OWNER = "alice"


@pytest.fixture
def service(init_db) -> AgentSessionService:
    """A service with a chip in the active test database."""
    ChipDocument(
        project_id=PROJECT,
        chip_id="chip-001",
        username=OWNER,
        size=4,
        system_info=SystemInfoModel(),
    ).insert()
    return AgentSessionService()


def _session(
    service: AgentSessionService,
    *,
    autonomy: AgentAutonomy = AgentAutonomy.AUTO,
    max_rounds_per_target: int = 3,
    created_by: str = OWNER,
) -> AgentSessionResponse:
    return service.create_session(
        project_id=PROJECT,
        username=created_by,
        body=CreateAgentSessionRequest(
            chip_id="chip-001",
            policy=AgentSessionPolicy(
                qids=["Q00"],
                allowed_tasks=["CheckRabi", "CheckChevron"],
                autonomy=autonomy,
                max_rounds_per_target=max_rounds_per_target,
                max_actions=10,
            ),
        ),
    )


def _step(
    version: int,
    *,
    key: str,
    task: str = "CheckRabi",
    repeat_of: str | None = None,
    autonomous: bool = True,
) -> SubmitAgentActionRequest:
    return SubmitAgentActionRequest(
        idempotency_key=key,
        expected_state_version=version,
        action_type=AgentActionType.RUN_TASK,
        task_name=task,
        qids=["Q00"],
        diagnosis="next step",
        autonomous=autonomous,
        repeat_of_action_id=repeat_of,
    )


def _submit(
    service: AgentSessionService, session_id: str, body: SubmitAgentActionRequest, user: str = OWNER
) -> Any:
    return service.submit_action(
        project_id=PROJECT, session_id=session_id, body=body, username=user
    )


def _version(session_id: str) -> int:
    doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert doc is not None
    return doc.state_version


def _budget(session_id: str) -> int:
    doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert doc is not None
    return doc.action_count


def _set_status(action_id: str, status: str) -> None:
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": action_id}, {"$set": {"execution_status": status}}
    )


def _refused(call: Any, status: int, match: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        call()
    assert exc_info.value.status_code == status
    assert match in str(exc_info.value.detail)


def test_an_autonomous_step_needs_the_signed_in_creator_of_an_auto_session(
    service: AgentSessionService,
) -> None:
    session = _session(service)
    # Another editor of the same project, and a request with no authenticated user.
    for user in ("bob", ""):
        _refused(
            lambda user=user: _submit(service, session.session_id, _step(0, key=f"k-{user}"), user),
            403,
            f"belongs to {OWNER}",
        )
    assert _budget(session.session_id) == 0
    assert AgentActionDocument.find({"session_id": session.session_id}).count() == 0

    action = _submit(service, session.session_id, _step(0, key="own"))
    assert action.decision == "authorized"
    assert action.autonomous is True

    confirm_each = _session(service, autonomy=AgentAutonomy.CONFIRM_EACH)
    _refused(
        lambda: _submit(service, confirm_each.session_id, _step(0, key="ce")),
        409,
        "autonomy confirm_each",
    )
    # The reviewed path, approved per call, is unchanged for any editor.
    reviewed = _submit(service, confirm_each.session_id, _step(0, key="r", autonomous=False), "bob")
    assert reviewed.decision == "authorized"
    assert reviewed.autonomous is False


def test_two_steps_from_one_snapshot_record_one_action(service: AgentSessionService) -> None:
    session = _session(service)
    first = _submit(service, session.session_id, _step(0, key="a", task="CheckRabi"))
    assert first.decision == "authorized"
    # The second step was decided from the same state version.
    _refused(
        lambda: _submit(service, session.session_id, _step(0, key="b", task="CheckChevron")),
        409,
        "state version mismatch",
    )
    assert _budget(session.session_id) == 1


def test_history_checks_use_every_action_the_state_version_counted(
    service: AgentSessionService,
) -> None:
    """A submission that crashed after it was counted is still seen by the next one."""
    session = _session(service)
    counted = _submit(service, session.session_id, _step(0, key="a"))
    # Simulate the crash window: the session update counted the action and stored its
    # record, but the record never reached the action collection.
    stored = AgentActionDocument.find_one({"action_id": counted.action_id}).run()
    assert stored is not None
    payload = raw_document(stored)
    stored.delete()
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session.session_id}, {"$set": {"pending_action": payload}}
    )

    # A step decided from the newer version but without the missing action is refused:
    # loading the session writes the record before the checks read the history.
    _refused(
        lambda: _submit(service, session.session_id, _step(1, key="b")),
        409,
        f"Action {counted.action_id} already proposes this measurement",
    )
    listed = service.list_actions(project_id=PROJECT, session_id=session.session_id)
    assert [item.action_id for item in listed.items] == [counted.action_id]
    doc = AgentSessionDocument.find_one({"session_id": session.session_id}).run()
    assert doc is not None
    assert doc.pending_action is None
    assert _budget(session.session_id) == 1


def test_running_repeats_and_rounds_are_refused_without_using_budget(
    service: AgentSessionService,
) -> None:
    session = _session(service, max_rounds_per_target=2)
    sid = session.session_id
    first = _submit(service, sid, _step(0, key="a"))

    _set_status(first.action_id, "queued")
    _refused(
        lambda: _submit(service, sid, _step(1, key="b", task="CheckChevron")), 409, "still running"
    )

    _set_status(first.action_id, "completed")
    _refused(
        lambda: _submit(service, sid, _step(1, key="c")), 409, "already ran this exact measurement"
    )
    _refused(
        lambda: _submit(
            service, sid, _step(1, key="d", task="CheckChevron", repeat_of=first.action_id)
        ),
        409,
        "is not a finished identical measurement",
    )
    assert _budget(sid) == 1

    # Measuring again on purpose is allowed once more; then the round budget holds.
    repeat = _submit(service, sid, _step(1, key="e", repeat_of=first.action_id))
    assert repeat.decision == "authorized"
    stored = AgentActionDocument.find_one({"action_id": repeat.action_id}).run()
    assert stored is not None
    assert stored.metadata["repeat_of_action_id"] == first.action_id
    _set_status(repeat.action_id, "completed")
    _refused(
        lambda: _submit(service, sid, _step(2, key="f", repeat_of=repeat.action_id)),
        409,
        "already ran 2 times",
    )
    assert _budget(sid) == 2
    # A different task on the same qubit has its own rounds.
    assert _submit(service, sid, _step(2, key="g", task="CheckChevron")).decision == "authorized"


def test_older_requests_hash_as_before() -> None:
    body = _step(0, key="old", autonomous=False)
    legacy = body.model_dump(mode="json", exclude={"autonomous", "repeat_of_action_id"})
    expected = hashlib.sha256(
        json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert AgentSessionService._request_hash(body) == expected
    assert AgentSessionService._request_hash(_step(0, key="old")) != expected


def _catalog(monkeypatch: pytest.MonkeyPatch) -> TaskFileService:
    monkeypatch.setattr("qdash.api.services.catalog_task_run.get_default_backend", lambda: "qubex")
    monkeypatch.setattr(
        "qdash.api.services.catalog_task_run.get_available_backends", lambda: ["qubex"]
    )
    monkeypatch.setattr(
        "qdash.api.services.catalog_task_run.is_task_available", lambda *_args: True
    )
    tasks = [
        TaskInfo(
            name=name,
            class_name=name,
            task_type="qubit",
            file_path=f"qubex/{name}.py",
            input_parameters={},
            run_parameters={},
        )
        for name in ("CheckRabi", "CheckChevron")
    ]
    return cast(
        "TaskFileService",
        SimpleNamespace(list_task_info=lambda *_args, **_kwargs: ListTaskInfoResponse(tasks=tasks)),
    )


class _FlowService:
    def __init__(self) -> None:
        self.runs = 0

    async def execute_single_task_from_snapshot(self, **_kwargs: object) -> object:
        self.runs += 1
        return SimpleNamespace(execution_id=f"exec-{self.runs}", flow_run_id=f"op-{self.runs}")


@pytest.mark.asyncio
async def test_an_autonomous_dispatch_waits_for_the_running_measurement(
    service: AgentSessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(service)
    sid = session.session_id
    # Two actions authorized through the reviewed path, before either ran.
    a = _submit(service, sid, _step(0, key="a", autonomous=False))
    b = _submit(service, sid, _step(1, key="b", task="CheckChevron", autonomous=False))
    flows = _FlowService()
    catalog = _catalog(monkeypatch)

    async def dispatch(action_id: str, user: str = OWNER, autonomous: bool = True) -> Any:
        return await service.execute_action(
            project_id=PROJECT,
            session_id=sid,
            action_id=action_id,
            body=ExecuteAgentActionRequest(autonomous=autonomous),
            flow_service=cast("FlowService", flows),
            task_file_service=catalog,
            username=user,
        )

    with pytest.raises(HTTPException) as other:
        await dispatch(a.action_id, user="bob")
    assert other.value.status_code == 403
    assert (await dispatch(a.action_id)).execution_status == "queued"

    with pytest.raises(HTTPException) as busy:
        await dispatch(b.action_id)
    assert busy.value.status_code == 409
    assert a.action_id in str(busy.value.detail)
    released = AgentActionDocument.find_one({"action_id": b.action_id}).run()
    assert released is not None
    assert released.execution_status == "not_started"
    assert released.dispatch_token is None
    assert flows.runs == 1

    # A reviewed dispatch keeps its behavior.
    assert (await dispatch(b.action_id, user="bob", autonomous=False)).execution_status == "queued"
    assert flows.runs == 2


def test_an_autonomous_intervention_needs_the_creator_of_an_auto_session(
    service: AgentSessionService,
) -> None:
    session = _session(service)

    def ask(user: str, key: str, session_id: str = session.session_id) -> Any:
        return service.interventions.create_intervention(
            project_id=PROJECT,
            session_id=session_id,
            username=user,
            body=CreateAgentInterventionRequest(
                idempotency_key=key,
                reason=AgentInterventionReason.AGENT_REQUEST,
                summary="s",
                question="q",
                autonomous=True,
            ),
        )

    _refused(lambda: ask("bob", "k-bob"), 403, f"belongs to {OWNER}")
    _refused(lambda: ask("", "k-none"), 403, f"belongs to {OWNER}")
    confirm_each = _session(service, autonomy=AgentAutonomy.CONFIRM_EACH)
    _refused(lambda: ask(OWNER, "k-ce", confirm_each.session_id), 409, "autonomy confirm_each")
    doc = AgentSessionDocument.find_one({"session_id": session.session_id}).run()
    assert doc is not None
    assert doc.status == "active"

    recorded = ask(OWNER, "k-own")
    assert recorded.session_status == "waiting_for_human"
