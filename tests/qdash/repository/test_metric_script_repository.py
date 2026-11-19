"""Tests for the metric script repository's compare-and-set save."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from qdash.datamodel.metric_script import MetricScriptRevision
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.metric_script import MetricScriptDocument
from qdash.repository.metric_script import MongoMetricScriptRepository


def _insert() -> MetricScriptDocument:
    doc = MetricScriptDocument(
        project_id="project-1",
        user_id="user-1",
        username="alice",
        name="Ratio",
        source="v1",
        revision=1,
        status="valid",
        revisions=[
            MetricScriptRevision(
                revision=1, source="v1", created_at=datetime.now(UTC), status="valid"
            )
        ],
        system_info=SystemInfoModel(),
    )
    doc.insert()
    return doc


def _load(script_id: str) -> MetricScriptDocument:
    doc = MetricScriptDocument.find_one({"script_id": script_id}).run()
    assert doc is not None
    return doc


def _raw(script_id: str) -> dict[str, Any] | None:
    raw: dict[str, Any] | None = MetricScriptDocument.get_motor_collection().find_one(
        {"script_id": script_id}
    )
    return raw


def _save_next(repo: MongoMetricScriptRepository, doc: MetricScriptDocument, source: str) -> bool:
    revision, updated_at = doc.revision, doc.system_info.updated_at
    doc.revision += 1
    doc.source = source
    doc.revisions.append(
        MetricScriptRevision(
            revision=doc.revision, source=source, created_at=datetime.now(UTC), status="valid"
        )
    )
    return repo.save_if_unchanged(doc, revision=revision, updated_at=updated_at)


def test_stale_copy_is_rejected_and_writes_nothing(init_db) -> None:
    repo = MongoMetricScriptRepository()
    script_id = _insert().script_id
    first, second = _load(script_id), _load(script_id)

    assert _save_next(repo, first, "first") is True
    stored = _raw(script_id)
    assert _save_next(repo, second, "second") is False

    assert _raw(script_id) == stored
    current = _load(script_id)
    assert current.revision == 2
    assert [(r.revision, r.source) for r in current.revisions] == [(1, "v1"), (2, "first")]


def test_metadata_save_with_same_revision_is_rejected(init_db) -> None:
    repo = MongoMetricScriptRepository()
    script_id = _insert().script_id
    first, second = _load(script_id), _load(script_id)

    revision, updated_at = first.revision, first.system_info.updated_at
    first.name = "Renamed"
    assert repo.save_if_unchanged(first, revision=revision, updated_at=updated_at) is True

    # Same revision number, but the update time no longer matches.
    revision, updated_at = second.revision, second.system_info.updated_at
    second.description = "lost"
    assert repo.save_if_unchanged(second, revision=revision, updated_at=updated_at) is False
    current = _load(script_id)
    assert current.name == "Renamed"
    assert current.description == ""


def test_save_within_the_same_millisecond_still_advances_update_time(init_db, monkeypatch) -> None:
    repo = MongoMetricScriptRepository()
    script_id = _insert().script_id
    doc = _load(script_id)
    frozen = doc.system_info.updated_at
    monkeypatch.setattr(SystemInfoModel, "update_time", lambda self: None)
    revision = doc.revision
    doc.name = "Renamed"

    assert repo.save_if_unchanged(doc, revision=revision, updated_at=frozen) is True
    # A concurrent writer that read before this save must not match the new state.
    assert _load(script_id).system_info.updated_at != frozen
    stale = _load(script_id)
    stale.description = "lost"
    assert repo.save_if_unchanged(stale, revision=revision, updated_at=frozen) is False
    assert _load(script_id).description == ""


def test_saved_shape_matches_plain_save(init_db) -> None:
    repo = MongoMetricScriptRepository()
    doc = _insert()
    doc.save()
    plain = _raw(doc.script_id)
    assert plain is not None

    loaded = _load(doc.script_id)
    assert repo.save_if_unchanged(
        loaded, revision=loaded.revision, updated_at=loaded.system_info.updated_at
    )
    stored = _raw(doc.script_id)
    assert stored is not None
    assert set(stored) == set(plain)
    plain["system_info"].pop("updated_at")
    stored["system_info"].pop("updated_at")
    assert stored == plain
