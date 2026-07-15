"""Tests for note router endpoints."""

from datetime import UTC, datetime

from qdash.datamodel.note import NoteCommentModel, NoteModel
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.cooldown import CooldownDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.metric_note import MetricNoteDocument
from qdash.dbmodel.migration import (
    migrate_legacy_target_notes_to_comments,
    migrate_metric_notes_to_latest_cooldown_target_notes,
    migrate_metric_notes_to_target_notes,
)
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.target_note import TargetNoteDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.dbmodel.user import UserDocument


def _create_project_user() -> dict[str, str]:
    user = UserDocument(
        username="note_user",
        hashed_password="hashed",
        access_token="note_token",
        default_project_id="note_project",
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectDocument(
        project_id="note_project",
        name="Note Project",
        owner_user_id=user.user_id,
        owner_username=user.username,
    ).insert()
    ProjectMembershipDocument(
        project_id="note_project",
        user_id=user.user_id,
        username=user.username,
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by=user.username,
    ).insert()
    return {"Authorization": "Bearer note_token", "X-Project-Id": "note_project"}


def _create_project_member(
    *,
    username: str = "note_editor",
    auth_value: str | None = None,
    role: ProjectRole = ProjectRole.EDITOR,
    system_role: SystemRole = SystemRole.USER,
) -> dict[str, str]:
    member_auth_value = auth_value or f"{username}_token"
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=member_auth_value,
        default_project_id="note_project",
        system_role=system_role,
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectMembershipDocument(
        project_id="note_project",
        user_id=user.user_id,
        username=user.username,
        role=role,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by=user.username,
    ).insert()
    return {"Authorization": f"Bearer {member_auth_value}", "X-Project-Id": "note_project"}


def _create_chip(*, cooldown_id: str | None = "cd-1") -> None:
    ChipDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        size=64,
        current_cooldown_id=cooldown_id,
        system_info=SystemInfoModel(),
    ).insert()


def _create_task_result(
    *,
    task_id: str,
    qid: str = "63",
    note: NoteModel | None = None,
    ai_review_note: NoteModel | None = None,
) -> None:
    TaskResultHistoryDocument(
        project_id="note_project",
        username="note_user",
        task_id=task_id,
        name="CheckQubitSpectroscopy",
        upstream_id="",
        status="completed",
        message="",
        input_parameters={},
        output_parameters={},
        output_parameter_names=[],
        note={},
        user_note=note or NoteModel(),
        ai_review_note=ai_review_note or NoteModel(),
        figure_path=[],
        json_figure_path=[],
        raw_data_path=[],
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, tzinfo=UTC),
        elapsed_time=1.0,
        task_type="qubit",
        system_info=SystemInfoModel(),
        qid=qid,
        execution_id="exec-1",
        tags=[],
        chip_id="chip-1",
    ).insert()


def _create_cooldown(
    *,
    cooldown_id: str = "cd-1",
    started_at: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    ended_at: datetime | None = datetime(2026, 1, 2, tzinfo=UTC),
) -> None:
    CooldownDocument(
        project_id="note_project",
        cooldown_id=cooldown_id,
        cryo_id="cryo-1",
        started_at=started_at,
        ended_at=ended_at,
        chip_ids=["chip-1"],
        system_info=SystemInfoModel(),
    ).insert()


def test_qubit_summary_notes_are_scoped_to_cooldown(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-2", started_at=datetime(2026, 1, 3, tzinfo=UTC))
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    response = test_client.put(
        "/chips/chip-1/qubits/21/note",
        headers=headers,
        params={"cooldown_id": "cd-1"},
        json={"content": "first cooldown summary"},
    )
    assert response.status_code == 200

    response = test_client.put(
        "/chips/chip-1/qubits/21/note",
        headers=headers,
        params={"cooldown_id": "cd-2"},
        json={"content": "second cooldown summary"},
    )
    assert response.status_code == 200

    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert doc.note.content == ""
    notes = {
        note.scope_key: note.note.content
        for note in TargetNoteDocument.find(TargetNoteDocument.target_id == "21").run()
    }
    assert notes == {
        "cooldown:cd-1": "first cooldown summary",
        "cooldown:cd-2": "second cooldown summary",
    }

    summary = test_client.get(
        "/chips/chip-1/notes-summary", headers=headers, params={"cooldown_id": "cd-1"}
    )
    assert summary.status_code == 200
    assert summary.json()["qubits"][0]["note"]["content"] == "first cooldown summary"

    summary = test_client.get(
        "/chips/chip-1/notes-summary", headers=headers, params={"cooldown_id": "cd-2"}
    )
    assert summary.status_code == 200
    assert summary.json()["qubits"][0]["note"]["content"] == "second cooldown summary"


def test_qubit_summary_note_entries_track_multiple_authors_and_edits(test_client, init_db):
    owner_headers = _create_project_user()
    editor_headers = _create_project_member()
    _create_chip(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-1")
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    first = test_client.post(
        "/chips/chip-1/qubits/21/note/comments",
        headers=owner_headers,
        params={"cooldown_id": "cd-1"},
        json={"content": "Owner observation"},
    )
    assert first.status_code == 200
    first_comment = first.json()
    assert first_comment["created_by"] == "note_user"
    assert first_comment["updated_by"] == "note_user"

    second = test_client.post(
        "/chips/chip-1/qubits/21/note/comments",
        headers=editor_headers,
        params={"cooldown_id": "cd-1"},
        json={"content": "Editor follow-up"},
    )
    assert second.status_code == 200
    assert second.json()["created_by"] == "note_editor"

    updated = test_client.put(
        f"/chips/chip-1/qubits/21/note/comments/{first_comment['comment_id']}",
        headers=owner_headers,
        params={"cooldown_id": "cd-1"},
        json={"content": "Owner observation, edited by owner"},
    )
    assert updated.status_code == 200
    updated_comment = updated.json()
    assert updated_comment["created_by"] == "note_user"
    assert updated_comment["updated_by"] == "note_user"
    assert updated_comment["content"] == "Owner observation, edited by owner"

    summary = test_client.get(
        "/chips/chip-1/notes-summary", headers=owner_headers, params={"cooldown_id": "cd-1"}
    )
    assert summary.status_code == 200
    comments = summary.json()["qubits"][0]["comments"]
    assert [comment["created_by"] for comment in comments] == ["note_user", "note_editor"]
    assert comments[0]["updated_by"] == "note_user"

    deleted = test_client.delete(
        f"/chips/chip-1/qubits/21/note/comments/{first_comment['comment_id']}",
        headers=owner_headers,
        params={"cooldown_id": "cd-1"},
    )
    assert deleted.status_code == 200

    summary = test_client.get(
        "/chips/chip-1/notes-summary", headers=owner_headers, params={"cooldown_id": "cd-1"}
    )
    assert summary.status_code == 200
    comments = summary.json()["qubits"][0]["comments"]
    assert len(comments) == 1
    assert comments[0]["comment_id"] == second.json()["comment_id"]


def test_target_note_entry_authorization_allows_author_or_system_admin(test_client, init_db):
    owner_headers = _create_project_user()
    editor_headers = _create_project_member(username="note_editor")
    admin_headers = _create_project_member(username="note_admin", system_role=SystemRole.ADMIN)
    _create_chip(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-1")
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    created = test_client.post(
        "/chips/chip-1/qubits/21/note/comments",
        headers=owner_headers,
        params={"cooldown_id": "cd-1"},
        json={"content": "Owner-only observation"},
    )
    assert created.status_code == 200
    comment_id = created.json()["comment_id"]

    forbidden_update = test_client.put(
        f"/chips/chip-1/qubits/21/note/comments/{comment_id}",
        headers=editor_headers,
        params={"cooldown_id": "cd-1"},
        json={"content": "Edited by another user"},
    )
    assert forbidden_update.status_code == 403

    forbidden_delete = test_client.delete(
        f"/chips/chip-1/qubits/21/note/comments/{comment_id}",
        headers=editor_headers,
        params={"cooldown_id": "cd-1"},
    )
    assert forbidden_delete.status_code == 403

    admin_update = test_client.put(
        f"/chips/chip-1/qubits/21/note/comments/{comment_id}",
        headers=admin_headers,
        params={"cooldown_id": "cd-1"},
        json={"content": "Edited by admin"},
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["created_by"] == "note_user"
    assert admin_update.json()["updated_by"] == "note_admin"

    admin_delete = test_client.delete(
        f"/chips/chip-1/qubits/21/note/comments/{comment_id}",
        headers=admin_headers,
        params={"cooldown_id": "cd-1"},
    )
    assert admin_delete.status_code == 200


def test_qubit_metric_notes_are_scoped_to_current_cooldown_fallback(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-1")
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    response = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        json={"content": "first cooldown note"},
    )

    assert response.status_code == 200
    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert doc.metric_notes == {}
    metric_note = MetricNoteDocument.find_one(MetricNoteDocument.target_id == "21").run()
    assert metric_note is not None
    assert metric_note.scope_key == "cooldown:cd-1"
    assert metric_note.note.content == "first cooldown note"

    summary = test_client.get("/chips/chip-1/notes-summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["qubits"][0]["metric_notes"]["t1"]["content"] == "first cooldown note"

    chip = ChipDocument.find_one(ChipDocument.chip_id == "chip-1").run()
    assert chip is not None
    chip.current_cooldown_id = "cd-2"
    chip.save()
    _create_cooldown(cooldown_id="cd-2", started_at=datetime(2026, 1, 3, tzinfo=UTC))

    summary = test_client.get("/chips/chip-1/notes-summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["qubits"] == []

    response = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        json={"content": "second cooldown note"},
    )

    assert response.status_code == 200
    notes = {
        note.scope_key: note.note.content
        for note in MetricNoteDocument.find(MetricNoteDocument.target_id == "21").run()
    }
    assert notes == {
        "cooldown:cd-1": "first cooldown note",
        "cooldown:cd-2": "second cooldown note",
    }


def test_coupling_metric_note_delete_uses_current_cooldown_scope(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-1")
    CouplingDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21-22",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    response = test_client.put(
        "/chips/chip-1/couplings/21-22/metric-notes/zx90_gate_fidelity",
        headers=headers,
        json={"content": "coupling note"},
    )
    assert response.status_code == 200

    response = test_client.delete(
        "/chips/chip-1/couplings/21-22/metric-notes/zx90_gate_fidelity",
        headers=headers,
    )

    assert response.status_code == 200
    assert list(MetricNoteDocument.find(MetricNoteDocument.target_id == "21-22").run()) == []


def test_metric_notes_without_active_cooldown_use_legacy_scope(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    response = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        json={"content": "legacy note"},
    )

    assert response.status_code == 200
    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert doc.metric_notes == {}
    metric_note = MetricNoteDocument.find_one(MetricNoteDocument.target_id == "21").run()
    assert metric_note is not None
    assert metric_note.scope_key == "global"
    assert metric_note.note.content == "legacy note"


def test_metric_notes_can_use_explicit_time_range_scope(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    params = {
        "start_at": "2026-02-01T00:00:00Z",
        "end_at": "2026-02-02T00:00:00Z",
    }
    response = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        params=params,
        json={"content": "range note"},
    )

    assert response.status_code == 200
    metric_note = MetricNoteDocument.find_one(MetricNoteDocument.target_id == "21").run()
    assert metric_note is not None
    assert metric_note.scope_type == "time_range"
    assert metric_note.scope_source == "manual_time_range"

    summary = test_client.get("/chips/chip-1/notes-summary", headers=headers, params=params)
    assert summary.status_code == 200
    assert summary.json()["qubits"][0]["metric_notes"]["t1"]["content"] == "range note"


def test_notes_summary_returns_time_range_notes_when_range_drifts(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    response = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        params={"start_at": "2026-02-01T00:00:00Z", "end_at": "2026-02-08T00:00:00Z"},
        json={"content": "range note"},
    )
    assert response.status_code == 200

    # The dashboard's relative range drifts forward between writing the note and
    # reading it back, so both bounds shift by a minute. The note must still be
    # returned (issue #1109).
    summary = test_client.get(
        "/chips/chip-1/notes-summary",
        headers=headers,
        params={"start_at": "2026-02-01T00:01:00Z", "end_at": "2026-02-08T00:01:00Z"},
    )
    assert summary.status_code == 200
    assert summary.json()["qubits"][0]["metric_notes"]["t1"]["content"] == "range note"


def test_notes_summary_excludes_time_range_notes_outside_window(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    response = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        params={"start_at": "2026-01-01T00:00:00Z", "end_at": "2026-01-08T00:00:00Z"},
        json={"content": "old range note"},
    )
    assert response.status_code == 200

    # A window that does not overlap the note's scope should not surface it.
    summary = test_client.get(
        "/chips/chip-1/notes-summary",
        headers=headers,
        params={"start_at": "2026-02-01T00:00:00Z", "end_at": "2026-02-08T00:00:00Z"},
    )
    assert summary.status_code == 200
    assert summary.json()["qubits"] == []


def test_notes_summary_prefers_exact_scope_when_time_ranges_overlap(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    # Two overlapping time-range notes for the same (qubit, metric) but with
    # slightly different bounds, so they land under distinct scope keys.
    older = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        params={"start_at": "2026-02-01T00:00:00Z", "end_at": "2026-02-08T00:00:00Z"},
        json={"content": "overlapping note"},
    )
    assert older.status_code == 200
    exact = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        params={"start_at": "2026-02-01T00:01:00Z", "end_at": "2026-02-08T00:01:00Z"},
        json={"content": "exact scope note"},
    )
    assert exact.status_code == 200
    assert len(list(MetricNoteDocument.find(MetricNoteDocument.target_id == "21").run())) == 2

    # The requested window matches the second note's scope key exactly while
    # still overlapping the first. The exact-scope note must win regardless of
    # edit order (issue #1109 follow-up).
    summary = test_client.get(
        "/chips/chip-1/notes-summary",
        headers=headers,
        params={"start_at": "2026-02-01T00:01:00Z", "end_at": "2026-02-08T00:01:00Z"},
    )
    assert summary.status_code == 200
    assert summary.json()["qubits"][0]["metric_notes"]["t1"]["content"] == "exact scope note"


def test_time_range_scope_infers_later_cooldown_document(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    _create_cooldown(
        cooldown_id="cd-later",
        started_at=datetime(2026, 3, 1, tzinfo=UTC),
        ended_at=datetime(2026, 3, 2, tzinfo=UTC),
    )
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()

    response = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        params={
            "start_at": "2026-03-01T03:00:00Z",
            "end_at": "2026-03-01T04:00:00Z",
        },
        json={"content": "inferred cooldown note"},
    )

    assert response.status_code == 200
    metric_note = MetricNoteDocument.find_one(MetricNoteDocument.target_id == "21").run()
    assert metric_note is not None
    assert metric_note.scope_key == "cooldown:cd-later"
    assert metric_note.scope_source == "inferred_from_range"


def test_notes_summary_classifies_old_ai_triage_task_notes(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    _create_task_result(
        task_id="task-ai",
        note=NoteModel(
            content=(
                "## AI triage *Reviewed by: ollama/gemma4:26b at "
                "2026-05-18T01:40:05.413718+00:00* **Review triage** "
                "- Decision: `PASS_WITH_NOTE`"
            ),
            updated_by="qdash-ai",
            updated_at=datetime(2026, 5, 19, tzinfo=UTC),
        ),
    )

    response = test_client.get("/chips/chip-1/notes-summary", headers=headers)

    assert response.status_code == 200
    task_note = response.json()["task_notes"][0]
    assert task_note["note"]["content"] == ""
    assert task_note["ai_review_note"]["content"].startswith("## AI triage")


def test_notes_summary_keeps_user_part_when_ai_review_prefix_exists(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    _create_task_result(
        task_id="task-user",
        note=NoteModel(
            content="## AI review\n\n- Decision: `PASS`\n\n---\n\noperator follow-up",
            updated_by="note_user",
            updated_at=datetime(2026, 5, 19, tzinfo=UTC),
        ),
    )

    response = test_client.get("/chips/chip-1/notes-summary", headers=headers)

    assert response.status_code == 200
    task_note = response.json()["task_notes"][0]
    assert task_note["note"]["content"] == "operator follow-up"
    assert task_note["ai_review_note"]["content"].startswith("## AI review")


def test_notes_summary_includes_task_results_with_only_ai_review_note(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)
    _create_task_result(
        task_id="task-ai-review-note",
        ai_review_note=NoteModel(
            content="## AI review\n\n- Decision: `REVIEW`\n",
            updated_by="qdash-ai",
            updated_at=datetime(2026, 5, 19, tzinfo=UTC),
        ),
    )

    response = test_client.get("/chips/chip-1/notes-summary", headers=headers)

    assert response.status_code == 200
    task_note = response.json()["task_notes"][0]
    assert task_note["task_id"] == "task-ai-review-note"
    assert task_note["note"]["content"] == ""
    assert task_note["ai_review_note"]["content"].startswith("## AI review")


def test_qubit_note_creates_missing_topology_target(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)

    response = test_client.put(
        "/chips/chip-1/qubits/21/note",
        headers=headers,
        json={"content": "No data yet; check wiring before next run."},
    )

    assert response.status_code == 200
    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert doc.data == {}
    assert doc.note.content == "No data yet; check wiring before next run."


def test_qubit_note_rejects_target_outside_topology(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)

    response = test_client.put(
        "/chips/chip-1/qubits/999/note",
        headers=headers,
        json={"content": "invalid target"},
    )

    assert response.status_code == 404
    assert QubitDocument.find_one(QubitDocument.qid == "999").run() is None


def test_coupling_note_creates_missing_topology_target(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)

    response = test_client.put(
        "/chips/chip-1/couplings/0-1/note",
        headers=headers,
        json={"content": "No coupling data yet."},
    )

    assert response.status_code == 200
    doc = CouplingDocument.find_one(CouplingDocument.qid == "0-1").run()
    assert doc is not None
    assert doc.data == {}
    assert doc.note.content == "No coupling data yet."


def test_qubit_metric_note_creates_missing_topology_target(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)

    response = test_client.put(
        "/chips/chip-1/qubits/21/metric-notes/t1",
        headers=headers,
        json={"content": "No metric data yet; check next cooldown."},
    )

    assert response.status_code == 200
    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert doc.data == {}
    metric_note = MetricNoteDocument.find_one(MetricNoteDocument.target_id == "21").run()
    assert metric_note is not None
    assert metric_note.scope_key == "global"
    assert metric_note.note.content == "No metric data yet; check next cooldown."

    summary = test_client.get("/chips/chip-1/notes-summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["qubits"][0]["metric_notes"]["t1"]["content"] == (
        "No metric data yet; check next cooldown."
    )


def test_coupling_metric_note_creates_missing_topology_target(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id=None)

    response = test_client.put(
        "/chips/chip-1/couplings/0-1/metric-notes/zx90_gate_fidelity",
        headers=headers,
        json={"content": "No coupling metric data yet."},
    )

    assert response.status_code == 200
    doc = CouplingDocument.find_one(CouplingDocument.qid == "0-1").run()
    assert doc is not None
    assert doc.data == {}
    metric_note = MetricNoteDocument.find_one(MetricNoteDocument.target_id == "0-1").run()
    assert metric_note is not None
    assert metric_note.scope_key == "global"
    assert metric_note.note.content == "No coupling metric data yet."

    summary = test_client.get("/chips/chip-1/notes-summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["couplings"][0]["metric_notes"]["zx90_gate_fidelity"]["content"] == (
        "No coupling metric data yet."
    )


def test_migrate_legacy_target_notes_to_comments(test_client, init_db):
    headers = _create_project_user()
    _create_chip(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-1")
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        note=NoteModel(
            content="Legacy global summary",
            updated_by="alice",
            updated_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
        system_info=SystemInfoModel(),
    ).insert()
    TargetNoteDocument(
        project_id="note_project",
        chip_id="chip-1",
        target_type="qubit",
        target_id="21",
        note=NoteModel(
            content="Cooldown summary",
            updated_by="bob",
            updated_at=datetime(2026, 1, 4, tzinfo=UTC),
        ),
        scope_type="cooldown",
        scope_key="cooldown:cd-1",
        cooldown_id="cd-1",
        scope_started_at=datetime(2026, 1, 1, tzinfo=UTC),
        scope_ended_at=None,
        scope_source="explicit_cooldown",
        system_info=SystemInfoModel(),
    ).insert()

    dry_run_stats = migrate_legacy_target_notes_to_comments(dry_run=True)
    assert dry_run_stats["legacy_notes_found"] == 2
    assert dry_run_stats["comments_created"] == 2
    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert doc.note.content == "Legacy global summary"

    execute_stats = migrate_legacy_target_notes_to_comments(dry_run=False)
    assert execute_stats["legacy_notes_found"] == 2
    assert execute_stats["comments_created"] == 2
    assert execute_stats["notes_cleared"] == 2

    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert doc.note.content == ""
    global_note = TargetNoteDocument.find_one(
        TargetNoteDocument.target_id == "21",
        TargetNoteDocument.scope_key == "global",
    ).run()
    assert global_note is None

    cooldown_note = TargetNoteDocument.find_one(
        TargetNoteDocument.scope_key == "cooldown:cd-1"
    ).run()
    assert cooldown_note is not None
    assert cooldown_note.note.content == ""
    assert len(cooldown_note.comments) == 2
    assert [comment.content for comment in cooldown_note.comments] == [
        "Cooldown summary",
        "Legacy global summary",
    ]
    assert cooldown_note.comments[0].created_by == "bob"
    assert cooldown_note.comments[1].created_by == "alice"
    assert cooldown_note.comments[1].created_at.replace(tzinfo=UTC) == datetime(
        2026, 1, 3, tzinfo=UTC
    )
    assert cooldown_note.comments[1].updated_at is None

    summary = test_client.get(
        "/chips/chip-1/notes-summary", headers=headers, params={"cooldown_id": "cd-1"}
    )
    assert summary.status_code == 200
    comments = summary.json()["qubits"][0]["comments"]
    assert [comment["content"] for comment in comments] == [
        "Cooldown summary",
        "Legacy global summary",
    ]
    assert [comment["created_by"] for comment in comments] == ["bob", "alice"]

    second_stats = migrate_legacy_target_notes_to_comments(dry_run=False)
    assert second_stats["legacy_notes_found"] == 0
    assert second_stats["comments_created"] == 0
    cooldown_note = TargetNoteDocument.find_one(
        TargetNoteDocument.scope_key == "cooldown:cd-1"
    ).run()
    assert cooldown_note is not None
    assert len(cooldown_note.comments) == 2


def test_migrate_legacy_target_notes_to_comments_relocates_prior_global_entries(
    test_client, init_db
):
    headers = _create_project_user()
    _create_chip(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-1")
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()
    TargetNoteDocument(
        project_id="note_project",
        chip_id="chip-1",
        target_type="qubit",
        target_id="21",
        note=NoteModel(),
        comments=[
            NoteCommentModel(
                comment_id="legacy-qubit-qubit-global",
                content="Previously migrated global summary",
                created_by="alice",
                created_at=datetime(2026, 1, 3, tzinfo=UTC),
                updated_by="alice",
            )
        ],
        scope_type="global",
        scope_key="global",
        cooldown_id=None,
        scope_started_at=None,
        scope_ended_at=None,
        scope_source="legacy_global",
        system_info=SystemInfoModel(),
    ).insert()

    stats = migrate_legacy_target_notes_to_comments(dry_run=False)

    assert stats["comments_relocated"] == 1
    assert TargetNoteDocument.find_one(TargetNoteDocument.scope_key == "global").run() is None
    cooldown_note = TargetNoteDocument.find_one(
        TargetNoteDocument.scope_key == "cooldown:cd-1"
    ).run()
    assert cooldown_note is not None
    assert len(cooldown_note.comments) == 1
    assert cooldown_note.comments[0].content == "Previously migrated global summary"

    summary = test_client.get(
        "/chips/chip-1/notes-summary", headers=headers, params={"cooldown_id": "cd-1"}
    )
    assert summary.status_code == 200
    assert summary.json()["qubits"][0]["comments"][0]["content"] == (
        "Previously migrated global summary"
    )


def test_migrate_metric_notes_to_target_notes_dry_run_and_execute(test_client, init_db):
    _create_project_user()
    _create_chip(cooldown_id="cd-1")
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        note=NoteModel(content="Pinned summary", updated_by="note_user"),
        system_info=SystemInfoModel(),
    ).insert()
    MetricNoteDocument(
        project_id="note_project",
        chip_id="chip-1",
        target_type="qubit",
        target_id="21",
        metric_key="t1",
        note=NoteModel(
            content="T1 has a long-tail outlier.",
            updated_by="alice",
            updated_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
        scope_type="cooldown",
        scope_key="cooldown:cd-1",
        cooldown_id="cd-1",
        scope_started_at=datetime(2026, 1, 1, tzinfo=UTC),
        scope_ended_at=datetime(2026, 1, 2, tzinfo=UTC),
        scope_source="current_cooldown",
        system_info=SystemInfoModel(),
    ).insert()

    dry_run_stats = migrate_metric_notes_to_target_notes(dry_run=True)
    assert dry_run_stats["metric_notes_found"] == 1
    assert dry_run_stats["targets_updated"] == 1
    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert doc.note.content == "Pinned summary"

    execute_stats = migrate_metric_notes_to_target_notes(dry_run=False)
    assert execute_stats["targets_updated"] == 1
    doc = QubitDocument.find_one(QubitDocument.qid == "21").run()
    assert doc is not None
    assert "Pinned summary" in doc.note.content
    assert "## Legacy metric notes" in doc.note.content
    assert "### t1" in doc.note.content
    assert "T1 has a long-tail outlier." in doc.note.content
    assert doc.note.updated_by == "alice"

    second_stats = migrate_metric_notes_to_target_notes(dry_run=False)
    assert second_stats["targets_updated"] == 0
    assert second_stats["targets_skipped_already_migrated"] == 1


def test_migrate_metric_notes_to_latest_cooldown_target_notes(test_client, init_db):
    _create_project_user()
    _create_chip(cooldown_id="cd-2")
    _create_cooldown(
        cooldown_id="cd-1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        ended_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    _create_cooldown(
        cooldown_id="cd-2",
        started_at=datetime(2026, 1, 3, tzinfo=UTC),
        ended_at=None,
    )
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()
    TargetNoteDocument(
        project_id="note_project",
        chip_id="chip-1",
        target_type="qubit",
        target_id="21",
        note=NoteModel(content="Latest CD summary", updated_by="note_user"),
        scope_type="cooldown",
        scope_key="cooldown:cd-2",
        cooldown_id="cd-2",
        scope_started_at=datetime(2026, 1, 3, tzinfo=UTC),
        scope_ended_at=None,
        scope_source="explicit_cooldown",
        system_info=SystemInfoModel(),
    ).insert()
    MetricNoteDocument(
        project_id="note_project",
        chip_id="chip-1",
        target_type="qubit",
        target_id="21",
        metric_key="t1",
        note=NoteModel(
            content="Old T1 note",
            updated_by="alice",
            updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        scope_type="cooldown",
        scope_key="cooldown:cd-1",
        cooldown_id="cd-1",
        scope_started_at=datetime(2026, 1, 1, tzinfo=UTC),
        scope_ended_at=datetime(2026, 1, 2, tzinfo=UTC),
        scope_source="explicit_cooldown",
        system_info=SystemInfoModel(),
    ).insert()

    dry_run_stats = migrate_metric_notes_to_latest_cooldown_target_notes(dry_run=True)
    assert dry_run_stats["targets_updated"] == 1
    target_note = TargetNoteDocument.find_one(TargetNoteDocument.scope_key == "cooldown:cd-2").run()
    assert target_note is not None
    assert target_note.note.content == "Latest CD summary"

    execute_stats = migrate_metric_notes_to_latest_cooldown_target_notes(dry_run=False)
    assert execute_stats["targets_updated"] == 1
    assert execute_stats["metric_notes_deleted"] == 0
    target_note = TargetNoteDocument.find_one(TargetNoteDocument.scope_key == "cooldown:cd-2").run()
    assert target_note is not None
    assert target_note.note.content.startswith("Latest CD summary")
    assert "## Migrated legacy metric notes" in target_note.note.content
    assert "### t1" in target_note.note.content
    assert "- Scope: `cooldown:cd-1`" in target_note.note.content
    assert "Old T1 note" in target_note.note.content
    assert target_note.note.updated_by == "alice"

    second_stats = migrate_metric_notes_to_latest_cooldown_target_notes(dry_run=False)
    assert second_stats["targets_updated"] == 0
    assert second_stats["targets_skipped_already_migrated"] == 1


def test_migrate_metric_notes_to_latest_cooldown_target_notes_can_delete_source(
    test_client, init_db
):
    _create_project_user()
    _create_chip(cooldown_id="cd-1")
    _create_cooldown(cooldown_id="cd-1")
    QubitDocument(
        project_id="note_project",
        username="note_user",
        chip_id="chip-1",
        qid="21",
        data={},
        system_info=SystemInfoModel(),
    ).insert()
    MetricNoteDocument(
        project_id="note_project",
        chip_id="chip-1",
        target_type="qubit",
        target_id="21",
        metric_key="t1",
        note=NoteModel(content="Delete after migration", updated_by="alice"),
        scope_type="global",
        scope_key="global",
        cooldown_id=None,
        scope_started_at=None,
        scope_ended_at=None,
        scope_source="legacy_global",
        system_info=SystemInfoModel(),
    ).insert()

    stats = migrate_metric_notes_to_latest_cooldown_target_notes(
        dry_run=False,
        delete_source=True,
    )

    assert stats["targets_updated"] == 1
    assert stats["metric_notes_deleted"] == 1
    assert list(MetricNoteDocument.find(MetricNoteDocument.target_id == "21").run()) == []
    target_note = TargetNoteDocument.find_one(TargetNoteDocument.target_id == "21").run()
    assert target_note is not None
    assert "Delete after migration" in target_note.note.content


def test_migrate_metric_notes_to_target_notes_reports_missing_targets(test_client, init_db):
    _create_project_user()
    MetricNoteDocument(
        project_id="note_project",
        chip_id="chip-1",
        target_type="coupling",
        target_id="0-1",
        metric_key="zx90_gate_fidelity",
        note=NoteModel(content="Needs follow-up", updated_by="note_user"),
        scope_type="global",
        scope_key="global",
        cooldown_id=None,
        scope_started_at=None,
        scope_ended_at=None,
        scope_source="legacy_global",
        system_info=SystemInfoModel(),
    ).insert()

    stats = migrate_metric_notes_to_target_notes(dry_run=False)
    assert stats["targets_missing"] == 1
    assert stats["targets_updated"] == 0
    assert stats["targets"][0]["action"] == "missing_target"
