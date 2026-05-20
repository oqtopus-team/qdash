"""Tests for note router endpoints."""

from datetime import UTC, datetime

from qdash.datamodel.note import NoteModel
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.cooldown import CooldownDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.metric_note import MetricNoteDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
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
    note: NoteModel,
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
        user_note=note,
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
