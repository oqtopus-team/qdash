"""Tests for the metric script repository's compare-and-set save and pin operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

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
    MongoMetricScriptRepository().insert(doc)
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
    revision, updated_at, version = doc.revision, doc.system_info.updated_at, doc.version
    doc.revision += 1
    doc.source = source
    doc.revisions.append(
        MetricScriptRevision(
            revision=doc.revision, source=source, created_at=datetime.now(UTC), status="valid"
        )
    )
    return repo.save_if_unchanged(doc, revision=revision, updated_at=updated_at, version=version)


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
    assert repo.save_if_unchanged(first, revision=revision, updated_at=updated_at, version=0)

    # Same revision number, but the update time no longer matches.
    revision, updated_at = second.revision, second.system_info.updated_at
    second.description = "lost"
    assert not repo.save_if_unchanged(second, revision=revision, updated_at=updated_at, version=0)
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

    assert repo.save_if_unchanged(doc, revision=revision, updated_at=frozen, version=0) is True
    # A concurrent writer that read before this save must not match the new state.
    assert _load(script_id).system_info.updated_at != frozen
    stale = _load(script_id)
    stale.description = "lost"
    assert repo.save_if_unchanged(stale, revision=revision, updated_at=frozen, version=0) is False
    assert _load(script_id).description == ""


def test_saved_shape_matches_plain_save(init_db) -> None:
    repo = MongoMetricScriptRepository()
    doc = _insert()
    doc.save()
    plain = _raw(doc.script_id)
    assert plain is not None

    loaded = _load(doc.script_id)
    assert repo.save_if_unchanged(
        loaded,
        revision=loaded.revision,
        updated_at=loaded.system_info.updated_at,
        version=loaded.version,
    )
    stored = _raw(doc.script_id)
    assert stored is not None
    assert set(stored) == set(plain)
    assert stored.pop("version") == plain.pop("version") + 1
    plain["system_info"].pop("updated_at")
    stored["system_info"].pop("updated_at")
    assert stored == plain


def _add_pin(
    repo: MongoMetricScriptRepository,
    script_id: str,
    revisions: list[int],
    *,
    dashboard_id: str = "dash_a",
    shared: bool = False,
    writer: str = "w1",
) -> bool:
    return repo.add_pin(
        project_id="project-1",
        script_id=script_id,
        dashboard_id=dashboard_id,
        revisions=revisions,
        shared=shared,
        writer=writer,
    )


def test_pin_changes_fail_a_save_that_read_before_them(init_db) -> None:
    repo = MongoMetricScriptRepository()
    script_id = _insert().script_id
    stale = _load(script_id)

    assert _add_pin(repo, script_id, [1]) is True
    pinned = _load(script_id)
    assert pinned.version == 1
    assert pinned.pins["dash_a"].revisions == [1]
    assert pinned.pins["dash_a"].shared is False
    assert pinned.pins["dash_a"].writer == "w1"
    # Same revision and update time as stored, but the pin moved the version on.
    assert _save_next(repo, stale, "lost") is False
    assert _load(script_id).revision == 1


def test_add_pin_requires_stored_revisions_and_sharing(init_db) -> None:
    repo = MongoMetricScriptRepository()
    script_id = _insert().script_id

    assert _add_pin(repo, script_id, [1, 2]) is False
    assert _add_pin(repo, script_id, [1], shared=True) is False  # the script is private
    assert _add_pin(repo, "ms_missing", [1]) is False
    # Claiming without revisions does not create an empty pin.
    assert _add_pin(repo, script_id, []) is False
    stored = _load(script_id)
    assert stored.pins == {}
    assert stored.version == 0


def test_add_pin_widens_and_narrow_pin_needs_the_last_writer(init_db) -> None:
    repo = MongoMetricScriptRepository()
    doc = _insert()
    assert _save_next(repo, doc, "v2") is True
    script_id = doc.script_id

    assert _add_pin(repo, script_id, [1], writer="w1") is True
    assert _add_pin(repo, script_id, [2], writer="w2") is True
    assert _load(script_id).pins["dash_a"].revisions == [1, 2]

    def narrow(revisions: list[int], writer: str) -> bool:
        return repo.narrow_pin(
            project_id="project-1",
            script_id=script_id,
            dashboard_id="dash_a",
            revisions=revisions,
            shared=False,
            writer=writer,
        )

    # w1 lost the pin to w2, so it must not drop w2's revision.
    assert narrow([1], "w1") is False
    assert _load(script_id).pins["dash_a"].revisions == [1, 2]
    assert narrow([2], "w2") is True
    assert _load(script_id).pins["dash_a"].revisions == [2]
    assert narrow([], "w2") is True
    assert _load(script_id).pins == {}


def test_clear_dashboard_pins_and_delete_if_unchanged(init_db) -> None:
    repo = MongoMetricScriptRepository()
    doc = _insert()
    assert _add_pin(repo, doc.script_id, [1], dashboard_id="dash_a") is True
    assert _add_pin(repo, doc.script_id, [1], dashboard_id="dash_b") is True

    repo.clear_dashboard_pins(project_id="project-1", dashboard_id="dash_a")
    stored = _load(doc.script_id)
    assert set(stored.pins) == {"dash_b"}
    assert stored.version == 3

    assert repo.delete_if_unchanged(stored, version=2) is False
    assert repo.delete_if_unchanged(stored, version=3) is True
    assert _raw(doc.script_id) is None


def test_documents_without_registry_require_migration_before_save(init_db) -> None:
    repo = MongoMetricScriptRepository()
    doc = _insert()
    collection = MetricScriptDocument.get_motor_collection()
    collection.update_one({"_id": doc.id}, {"$unset": {"version": "", "pins": ""}})

    legacy = _load(doc.script_id)
    assert legacy.version == 0
    assert _save_next(repo, legacy, "v2") is False
    migrated = repo.get(project_id=doc.project_id, script_id=doc.script_id)
    assert migrated is not None and migrated.pins_initialized
    assert migrated.version == 1
    assert _save_next(repo, migrated, "v2") is True
    assert _load(doc.script_id).version == 2


@pytest.mark.parametrize("dashboard_id", ["", "dash.a", "$where"])
def test_pin_keys_reject_paths_and_operators(init_db, dashboard_id: str) -> None:
    repo = MongoMetricScriptRepository()
    script_id = _insert().script_id
    with pytest.raises(ValueError, match="dashboard ID"):
        _add_pin(repo, script_id, [1], dashboard_id=dashboard_id)


@pytest.mark.parametrize("marker", [None, 1])
def test_old_initialized_registry_cannot_be_saved_or_deleted(init_db, marker) -> None:
    repo = MongoMetricScriptRepository()
    doc = _insert()
    collection = MetricScriptDocument.get_motor_collection()
    collection.update_one(
        {"_id": doc.id},
        {"$set": {"pins_schema_version": marker}}
        if marker
        else {"$unset": {"pins_schema_version": ""}},
    )
    stale = _load(doc.script_id)
    assert not repo.delete_if_unchanged(stale, version=stale.version)
    assert not _save_next(repo, stale, "lost")
    current = repo.get(project_id=doc.project_id, script_id=doc.script_id)
    assert current is not None and current.pins_schema_version == 2
    assert not repo.delete_if_unchanged(stale, version=stale.version - 1)
    assert _save_next(repo, current, "next")
