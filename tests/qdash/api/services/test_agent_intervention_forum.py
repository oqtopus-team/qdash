"""Tests for the Forum thread QDash opens for each agent intervention."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from qdash.api.schemas.agent_session import SubmitAgentActionRequest
from qdash.api.schemas.forum import ForumPostCreate, ForumPostUpdate
from qdash.api.services.agent_intervention_forum import (
    MAX_CONTENT_CHARS,
    AgentInterventionForumService,
)
from qdash.api.services.agent_intervention_service import (
    AgentInterventionService,
    run_notification_sweeper,
)
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.api.services.forum_service import ForumService
from qdash.client.services.models import (
    AgentInterventionForumThreadResponse as ClientForumThread,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentActionType
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentInterventionDocument, AgentSessionDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.forum import ForumCategoryDocument, ForumLabelDocument, ForumPostDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from tests.qdash.api.services.test_agent_intervention_service import (
    PROJECT,
    FakeSlack,
    _completed_run,
    _notifier,
    _request,
    _session,
)

OTHER_PROJECT = "project-2"


@pytest.fixture
def slack() -> FakeSlack:
    return FakeSlack()


@pytest.fixture
def interventions(init_db, slack: FakeSlack) -> AgentInterventionService:
    """An intervention service with Slack agent notifications turned off."""
    ChipDocument(
        project_id=PROJECT,
        chip_id="chip-001",
        username="tester",
        size=4,
        system_info=SystemInfoModel(),
    ).insert()
    ProjectDocument(
        project_id=PROJECT, name="Lab A", owner_user_id="u-1", owner_username="tester"
    ).insert()
    return AgentInterventionService(notifier=_notifier(slack, enabled=False))


@pytest.fixture
def sessions(interventions: AgentInterventionService) -> AgentSessionService:
    return AgentSessionService(intervention_service=interventions)


@pytest.fixture
def forum_threads() -> AgentInterventionForumService:
    return AgentInterventionForumService()


def _open(sessions: AgentSessionService, interventions: AgentInterventionService, **request: Any):
    """An explicit intervention citing a finished run, recorded but without its thread yet."""
    session = _session(sessions)
    action_id = _completed_run(sessions, session.session_id)
    opened = interventions.create_intervention(
        project_id=PROJECT,
        session_id=session.session_id,
        username="tester",
        body=_request(action_id, **request),
    )
    return session, opened


def _record(intervention_id: str) -> AgentInterventionDocument:
    doc = AgentInterventionDocument.find_one({"intervention_id": intervention_id}).run()
    assert doc is not None
    return doc


def _threads(project_id: str = PROJECT) -> list[ForumPostDocument]:
    return ForumPostDocument.find({"project_id": project_id, "parent_id": None}).to_list()


def _make_due(intervention_id: str) -> None:
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": intervention_id},
        {"$set": {"forum_thread.next_attempt_at": now() - timedelta(seconds=1)}},
    )


def test_an_explicit_intervention_opens_one_linked_thread_without_slack(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
    slack: FakeSlack,
) -> None:
    session, opened = _open(sessions, interventions)
    assert opened.forum_thread is not None
    assert opened.forum_thread.status.value == "pending"

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    record = _record(opened.intervention_id)
    assert record.forum_thread is not None
    assert record.forum_thread.status.value == "created"
    assert record.forum_thread.post_id == str(thread.id)
    assert record.forum_thread.number == thread.number
    # Slack is off: nothing was posted, and the thread exists anyway.
    assert record.notification.status.value == "disabled"
    assert slack.calls == []
    # Typed linkage, separate from the labels.
    assert thread.agent_intervention_id == opened.intervention_id
    assert thread.agent_session_id == session.session_id
    assert thread.labels == ["agent", "calibration", "question"]
    # Written by QDash, not by the session's user or an expert.
    assert thread.username == "qdash"
    assert thread.user_id is None
    assert thread.category == "qubit"
    assert (thread.chip_id, thread.target_type, thread.target_id) == ("chip-001", "qubit", "Q00")
    assert thread.task_id == "task-a-1"
    assert thread.status == "open"
    assert thread.title is not None
    assert thread.title.startswith("Agent question (chip-001 Q00): Is the Rabi oscillation")

    content = thread.content
    assert "QDash opened this thread for a calibration agent's request" in content
    # Timeless: the thread never claims a status that can go stale.
    assert "answered" not in content
    assert "shows the request's current status" in content
    assert "Shortened" not in content
    assert (
        f"(/agent-sessions/{session.session_id}/interventions/{opened.intervention_id}"
        f"?project={PROJECT})" in content
    )
    assert f"(/agent-sessions/{session.session_id}?project={PROJECT})" in content
    assert f"(/execution/chip-001/sessions/{session.session_id}?project={PROJECT})" in content
    assert f"[task result](/task-results/task-a-1?project={PROJECT})" in content
    assert f"[execution](/execution/chip-001/exec-a-1?project={PROJECT})" in content
    assert "Unknown outcome" in content

    # The response reports the link.
    shown = interventions.get_intervention(
        project_id=PROJECT, session_id=session.session_id, intervention_id=opened.intervention_id
    )
    assert shown.forum_thread is not None
    assert shown.forum_thread.post_id == str(thread.id)
    # The thread changes nothing about the intervention or the pause.
    assert shown.status.value == "open"
    assert shown.session_status.value == "waiting_for_human"


def test_a_request_human_action_opens_one_thread(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    session = _session(sessions)
    version = sessions.get_session(project_id=PROJECT, session_id=session.session_id).state_version
    action = sessions.submit_action(
        project_id=PROJECT,
        session_id=session.session_id,
        username="agent-user",
        body=SubmitAgentActionRequest(
            idempotency_key="human-1",
            expected_state_version=version,
            action_type=AgentActionType.REQUEST_HUMAN,
            diagnosis="The resonator dip moved by 5 MHz; I do not know why.",
        ),
    )
    assert action.intervention_id is not None

    forum_threads.ensure_thread(action.intervention_id)
    forum_threads.ensure_thread(action.intervention_id)
    assert forum_threads.sweep() == 0

    [thread] = _threads()
    assert thread.agent_intervention_id == action.intervention_id
    assert thread.labels == ["agent", "calibration", "question"]
    assert "a `request_human` action" in thread.content
    assert "The agent cited no task results or executions." in thread.content
    assert action.action_id in thread.content.replace("\\-", "-")
    assert thread.task_id is None
    # The session targets are recorded on the session, not on the action: no target.
    assert thread.category == "system"
    assert _record(action.intervention_id).forum_thread.status.value == "created"  # type: ignore[union-attr]


def test_a_replayed_request_and_repeated_attempts_keep_one_thread(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    session, opened = _open(sessions, interventions)
    forum_threads.ensure_thread(opened.intervention_id)

    replay = interventions.create_intervention(
        project_id=PROJECT,
        session_id=session.session_id,
        username="tester",
        body=_request(opened.attempts[0].action_id),
    )
    assert replay.intervention_id == opened.intervention_id
    forum_threads.ensure_thread(replay.intervention_id)
    _make_due(opened.intervention_id)
    forum_threads.sweep()

    assert len(_threads()) == 1
    assert _record(opened.intervention_id).forum_thread.attempts == 1  # type: ignore[union-attr]


def test_a_crash_after_the_insert_records_the_existing_thread(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    _, opened = _open(sessions, interventions)
    forum_threads.ensure_thread(opened.intervention_id)
    [thread] = _threads()
    # The process died after inserting the thread, before the link was stored; the thread
    # was archived meanwhile, and the lease ran out.
    ForumPostDocument.get_motor_collection().update_one(
        {"_id": thread.id}, {"$set": {"is_deleted": True}}
    )
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": opened.intervention_id},
        {
            "$set": {
                "forum_thread.status": "creating",
                "forum_thread.post_id": None,
                "forum_thread.number": None,
                "forum_thread.lease_until": now() - timedelta(seconds=1),
            }
        },
    )

    assert forum_threads.sweep() == 1

    assert len(_threads()) == 1
    state = _record(opened.intervention_id).forum_thread
    assert state is not None
    assert state.status.value == "created"
    assert state.post_id == str(thread.id)


def test_a_racing_attempt_records_the_thread_the_other_inserted(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, opened = _open(sessions, interventions)
    record = _record(opened.intervention_id)
    # Another worker, whose lease ran out mid-attempt, inserts the thread between this
    # attempt's lookup and its insert.
    winner = ForumPostDocument(
        project_id=PROJECT,
        number=99,
        category="other",
        username="qdash",
        title="first",
        content="first",
        agent_intervention_id=record.intervention_id,
        agent_session_id=record.session_id,
    )
    original_lookup = AgentInterventionForumService._existing_thread
    calls = {"count": 0}

    def lookup_racing(doc: AgentInterventionDocument) -> ForumPostDocument | None:
        calls["count"] += 1
        if calls["count"] == 1:
            winner.insert()
            return None
        return original_lookup(doc)

    monkeypatch.setattr(
        AgentInterventionForumService, "_existing_thread", staticmethod(lookup_racing)
    )

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    assert thread.id == winner.id
    assert _record(opened.intervention_id).forum_thread.post_id == str(winner.id)  # type: ignore[union-attr]


def test_a_held_lease_blocks_a_second_attempt(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    _, opened = _open(sessions, interventions)
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": opened.intervention_id},
        {
            "$set": {
                "forum_thread.status": "creating",
                "forum_thread.lease_until": now() + timedelta(seconds=60),
            }
        },
    )

    forum_threads.ensure_thread(opened.intervention_id)
    assert forum_threads.sweep() == 0
    assert _threads() == []


def test_a_forum_failure_keeps_the_pause_and_is_retried(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, opened = _open(sessions, interventions)

    def broken(_: str) -> int:
        raise RuntimeError("forum counter unavailable: mongodb://user:secret@host")

    monkeypatch.setattr(ForumService, "_next_thread_number", staticmethod(broken))
    forum_threads.ensure_thread(opened.intervention_id)

    state = _record(opened.intervention_id).forum_thread
    assert state is not None
    assert state.status.value == "pending"
    assert state.attempts == 1
    # Only the error type is kept, never its text.
    assert state.last_error == "RuntimeError"
    assert state.next_attempt_at is not None
    assert state.lease_until is None
    assert _threads() == []
    shown = interventions.get_intervention(
        project_id=PROJECT, session_id=session.session_id, intervention_id=opened.intervention_id
    )
    assert shown.status.value == "open"
    assert shown.session_status.value == "waiting_for_human"

    # Not due yet: the sweeper leaves it alone.
    assert forum_threads.sweep() == 0
    monkeypatch.undo()
    _make_due(opened.intervention_id)
    assert forum_threads.sweep() == 1

    [thread] = _threads()
    state = _record(opened.intervention_id).forum_thread
    assert state is not None
    assert state.status.value == "created"
    assert state.attempts == 2
    assert state.last_error == ""
    assert state.post_id == str(thread.id)


def test_an_archived_thread_is_never_recreated(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    _, opened = _open(sessions, interventions)
    forum_threads.ensure_thread(opened.intervention_id)
    [thread] = _threads()
    ForumService().delete_post(
        project_id=PROJECT, post_id=str(thread.id), username="tester", role=ProjectRole.OWNER
    )

    forum_threads.ensure_thread(opened.intervention_id)
    _make_due(opened.intervention_id)
    forum_threads.sweep()

    assert len(_threads()) == 1
    assert _record(opened.intervention_id).forum_thread.post_id == str(thread.id)  # type: ignore[union-attr]


def test_deleted_and_renamed_labels_are_respected(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    forum = ForumService()
    forum.list_labels(project_id=PROJECT)
    forum.delete_label(project_id=PROJECT, key="question")
    forum.update_label(
        project_id=PROJECT, key="agent", name="ai-agent", description=None, color=None
    )
    _, opened = _open(sessions, interventions)

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    assert thread.labels == ["agent", "calibration"]
    question = ForumLabelDocument.find_one({"project_id": PROJECT, "key": "question"}).run()
    assert question is not None
    assert question.is_deleted is True
    agent = ForumLabelDocument.find_one({"project_id": PROJECT, "key": "agent"}).run()
    assert agent is not None
    assert agent.name == "ai-agent"


def test_a_project_without_any_agent_label_still_gets_its_thread(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    forum = ForumService()
    forum.list_labels(project_id=PROJECT)
    for key in ("agent", "calibration", "question"):
        forum.delete_label(project_id=PROJECT, key=key)
    _, opened = _open(sessions, interventions)

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    assert thread.labels == []


def test_archived_categories_are_skipped_and_never_restored(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    forum = ForumService()
    forum.list_categories(project_id=PROJECT)
    forum.delete_category(project_id=PROJECT, key="qubit")
    forum.delete_category(project_id=PROJECT, key="system")
    _, opened = _open(sessions, interventions)

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    assert thread.category == "other"
    archived = ForumCategoryDocument.find(
        {"project_id": PROJECT, "key": {"$in": ["qubit", "system"]}}
    ).to_list()
    assert all(category.is_archived for category in archived)


def test_the_first_active_category_is_used_when_no_preferred_one_is_active(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    forum = ForumService()
    forum.list_categories(project_id=PROJECT)
    for key in ("qubit", "system", "other", "control"):
        forum.delete_category(project_id=PROJECT, key=key)
    _, opened = _open(sessions, interventions)

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    assert thread.category == "coupling"


def test_threads_stay_in_the_intervention_project(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    # Another project has its own labels, with "agent" deleted there only.
    forum = ForumService()
    forum.list_labels(project_id=OTHER_PROJECT)
    forum.delete_label(project_id=OTHER_PROJECT, key="agent")
    _, opened = _open(sessions, interventions)
    # The cited task result left the project after the intervention was recorded, and a
    # result with the same id exists in the other project.
    TaskResultHistoryDocument.get_motor_collection().update_one(
        {"project_id": PROJECT, "task_id": "task-a-1"},
        {"$set": {"project_id": OTHER_PROJECT}},
    )

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    assert thread.labels == ["agent", "calibration", "question"]
    assert _threads(OTHER_PROJECT) == []
    # No link to a result that is not in the project.
    assert "/task-results/task-a-1" not in thread.content
    assert "task result task\\-a\\-1 (not found)" in thread.content
    assert thread.task_id is None


def test_the_agent_text_cannot_add_links_images_or_markup(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    hostile = (
        "Ask @owner: [open](https://evil.example/x) ![p](https://evil.example/p.png) "
        "<img src=x> www.evil.example\n# Heading\n```mermaid\ngraph TD\n```"
    )
    _, opened = _open(sessions, interventions, question=hostile, summary=hostile)

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    content = thread.content
    # "@owner" stays visible text: the Forum renderer may still style it as a mention, but no
    # mention notification is sent for a thread QDash opens.
    for markup in (
        "[open](",
        "![p](",
        "<img",
        "https://",
        "www.evil",
        "# Heading",
        "```",
        "@owner",
    ):
        # Every punctuation character of the agent's text is backslash-escaped.
        assert re.search(r"(?<!\\)" + re.escape(markup), content) is None, markup
    assert "\\[open\\]\\(https\\:" in content
    assert "\\<img src\\=x\\>" in content
    # The title is plain text the UI escapes; it is bounded.
    assert thread.title is not None
    assert len(thread.title) <= 200


def test_an_intervention_from_before_forum_threads_gets_none(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    session, opened = _open(sessions, interventions)
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": opened.intervention_id}, {"$unset": {"forum_thread": ""}}
    )

    forum_threads.ensure_thread(opened.intervention_id)
    assert forum_threads.sweep() == 0

    assert _threads() == []
    shown = interventions.get_intervention(
        project_id=PROJECT, session_id=session.session_id, intervention_id=opened.intervention_id
    )
    assert shown.forum_thread is None


def test_a_pause_whose_record_was_never_written_still_gets_its_thread(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    session, opened = _open(sessions, interventions)
    # Simulate a crash between the pausing update and the record write.
    raw = AgentInterventionDocument.get_motor_collection().find_one(
        {"intervention_id": opened.intervention_id}, {"_id": 0}
    )
    AgentInterventionDocument.get_motor_collection().delete_one(
        {"intervention_id": opened.intervention_id}
    )
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session.session_id},
        {"$set": {"pending_intervention": {"intervention": raw, "action": None}}},
    )

    interventions.materialize_pending_pauses()
    assert forum_threads.sweep() == 1

    [thread] = _threads()
    assert thread.agent_intervention_id == opened.intervention_id


def test_the_sweeper_opens_threads_when_slack_is_off(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
) -> None:
    _, opened = _open(sessions, interventions)

    async def run() -> None:
        task = run_notification_sweeper(interventions, interval_seconds=0.01)
        for _ in range(200):
            await asyncio.sleep(0.01)
            if _threads():
                break
        task.cancel()

    asyncio.run(run())

    [thread] = _threads()
    assert thread.agent_intervention_id == opened.intervention_id


def test_a_failing_pause_recovery_does_not_stop_thread_delivery(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, opened = _open(sessions, interventions)
    recoveries: list[int] = []

    def failing_recovery() -> int:
        recoveries.append(1)
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(interventions, "materialize_pending_pauses", failing_recovery)

    async def run() -> None:
        task = run_notification_sweeper(interventions, interval_seconds=0.01)
        for _ in range(200):
            await asyncio.sleep(0.01)
            if _threads():
                break
        task.cancel()

    asyncio.run(run())

    assert recoveries
    [thread] = _threads()
    assert thread.agent_intervention_id == opened.intervention_id


def test_stored_naive_thread_timestamps_parse_in_the_python_client(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    session, opened = _open(sessions, interventions)
    forum_threads.ensure_thread(opened.intervention_id)
    naive = datetime(2026, 11, 26, 9, 30)
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": opened.intervention_id},
        {
            "$set": {
                "forum_thread.last_attempt_at": naive,
                "forum_thread.next_attempt_at": naive,
                "forum_thread.created_at": naive,
            }
        },
    )

    shown = interventions.get_intervention(
        project_id=PROJECT, session_id=session.session_id, intervention_id=opened.intervention_id
    )
    payload = shown.forum_thread.model_dump(mode="json") if shown.forum_thread else None
    assert payload is not None

    parsed = ClientForumThread.model_validate(payload)
    expected = naive.replace(tzinfo=UTC)
    assert parsed.last_attempt_at == expected
    assert parsed.next_attempt_at == expected
    assert parsed.created_at == expected


def _expire_lease(intervention_id: str) -> None:
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": intervention_id},
        {"$set": {"forum_thread.lease_until": now() - timedelta(seconds=1)}},
    )


def test_a_stale_failed_attempt_cannot_overwrite_a_newer_result(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, opened = _open(sessions, interventions)
    stale, newer = AgentInterventionForumService(), AgentInterventionForumService()

    def slow_then_failing(doc: AgentInterventionDocument) -> ForumPostDocument:
        # The attempt stalls past its lease; a newer attempt claims and opens the thread.
        _expire_lease(doc.intervention_id)
        newer.ensure_thread(doc.intervention_id)
        raise RuntimeError("timed out")

    monkeypatch.setattr(stale, "_insert_thread", slow_then_failing)
    stale.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    state = _record(opened.intervention_id).forum_thread
    assert state is not None
    assert state.status.value == "created"
    assert state.attempts == 2
    assert state.post_id == str(thread.id)
    assert state.last_error == ""
    assert state.next_attempt_at is None
    assert state.lease_until is None


def test_a_stale_successful_attempt_cannot_overwrite_a_newer_claim(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, opened = _open(sessions, interventions)
    stale = AgentInterventionForumService()
    original_insert = stale._insert_thread
    held_until = now() + timedelta(seconds=60)

    def insert_then_stall(doc: AgentInterventionDocument) -> ForumPostDocument:
        post = original_insert(doc)
        # The attempt stalls past its lease after the insert; a newer attempt claims it.
        AgentInterventionDocument.get_motor_collection().update_one(
            {"intervention_id": doc.intervention_id},
            {
                "$set": {"forum_thread.lease_until": held_until},
                "$inc": {"forum_thread.attempts": 1},
            },
        )
        return post

    monkeypatch.setattr(stale, "_insert_thread", insert_then_stall)
    stale.ensure_thread(opened.intervention_id)

    # The newer claim stands: its lease is not released and no outcome was recorded.
    state = _record(opened.intervention_id).forum_thread
    assert state is not None
    assert state.status.value == "creating"
    assert state.attempts == 2
    assert state.post_id is None
    assert state.lease_until is not None

    # When that claim lapses too, the next attempt records the thread already inserted.
    _expire_lease(opened.intervention_id)
    assert forum_threads.sweep() == 1
    [thread] = _threads()
    state = _record(opened.intervention_id).forum_thread
    assert state is not None
    assert state.status.value == "created"
    assert state.attempts == 3
    assert state.post_id == str(thread.id)


def test_the_whole_body_fits_the_forum_limit_in_the_worst_case(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
) -> None:
    session, opened = _open(sessions, interventions)
    # Every character escapes to two, and every line break becomes a hard break.
    worst = "@\n" * 1000
    attempt = {
        "node_id": "n" * 200,
        "task_name": "[" * 200,
        "qid": "]" * 200,
        "transition": "*" * 64,
        "status": "_" * 200,
        "reason": "<" * 1000,
        "action_id": opened.attempts[0].action_id,
        "execution_id": "exec-a-1",
        "task_id": "task-a-1",
        "evaluation_id": "e" * 64,
    }
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": opened.intervention_id},
        {
            "$set": {
                "question": worst,
                "summary": worst,
                "task_name": "!" * 200,
                "node_id": "#" * 200,
                "attempts": [attempt] * 30,
            }
        },
    )

    forum_threads.ensure_thread(opened.intervention_id)

    [thread] = _threads()
    content = thread.content
    assert len(content) <= MAX_CONTENT_CHARS
    # The thread stays editable through the Forum's own schemas.
    ForumPostUpdate(content=content)
    ForumPostCreate(category=thread.category, title=thread.title, content=content)
    # The essential links are kept.
    intervention_link = (
        f"(/agent-sessions/{session.session_id}/interventions/{opened.intervention_id}"
        f"?project={PROJECT})"
    )
    assert intervention_link in content
    assert f"(/agent-sessions/{session.session_id}?project={PROJECT})" in content
    # The question and summary are shortened, each pointing to the full text.
    assert content.count("(Shortened. The full text is on the [intervention page]") == 2
    # Evidence entries are kept whole, and the rest are counted with a pointer.
    evidence = content.split("### Evidence", 1)[1]
    shown = re.findall(r"^(\d+)\. ", evidence, flags=re.M)
    assert 0 < len(shown) < 30
    assert evidence.count("Agent's note:") == len(shown)
    assert evidence.count("[task result](") == len(shown)
    assert f"{30 - len(shown)} more attempts are on the [intervention page]" in evidence
    # Nothing was cut inside an escape: no line ends in a lone backslash, and every
    # unescaped "[" opens one of QDash's own links.
    assert re.search(r"(?<!\\)(?:\\\\)*\\$", content, flags=re.M) is None
    opened_brackets = re.findall(r"(?<!\\)\[([^\]]*)\]\(", content)
    assert len(opened_brackets) == len(re.findall(r"(?<!\\)\[", content))
    assert set(opened_brackets) <= {
        "intervention page",
        "graph",
        "task result",
        "execution",
        session.session_id.replace("-", "\\-"),
    }


@pytest.mark.parametrize(
    ("task_name_length", "note_length"), [(14, 337), (15, 228), (24, 336), (32, 227)]
)
def test_a_body_at_the_limit_keeps_its_sections_instead_of_the_links_only_fallback(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    forum_threads: AgentInterventionForumService,
    task_name_length: int,
    note_length: int,
) -> None:
    _, opened = _open(sessions, interventions)
    doc = _record(opened.intervention_id)
    attempt = doc.attempts[0].model_copy(update={"reason": "r" * note_length})
    # The task name moves the fixed part and the note moves where whole evidence entries
    # end; these pairs make the kept evidence and both shortened texts fill their shares
    # exactly, which used to overrun the limit by the uncounted separators.
    candidate = doc.model_copy(
        update={
            "question": "a@" * 1000,
            "summary": "b@" * 1000,
            "task_name": "t" * task_name_length,
            "attempts": [attempt] * 30,
        }
    )

    content = AgentInterventionForumService.content(candidate, forum_threads._evidence(doc))

    assert len(content) <= MAX_CONTENT_CHARS
    assert "did not fit in a Forum post" not in content
    assert content.count("(Shortened. The full text is on the [intervention page]") == 2
    evidence = content.split("### Evidence", 1)[1]
    shown = len(re.findall(r"^(\d+)\. ", evidence, flags=re.M))
    assert shown > 0
    assert f"{30 - shown} more attempts are on the [intervention page]" in evidence
