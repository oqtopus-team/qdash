"""Tests for task-knowledge drafts: a zipped task directory, stored per project."""

from __future__ import annotations

import base64
import hashlib
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from qdash.api.services import knowledge_draft_service as kds
from qdash.datamodel import task_knowledge as tk
from tests.qdash.api._knowledge_drafts import GENERATOR, INDEX, PNG, RABI, make_zip

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A config root whose task-knowledge checkout holds only the generator."""
    repo = tmp_path / "config" / "task-knowledge"
    repo.mkdir(parents=True)
    (repo / "generate.py").write_text(GENERATOR, encoding="utf-8")
    monkeypatch.setattr(
        "qdash.common.config.loader.ConfigLoader.get_config_dir",
        classmethod(lambda cls: tmp_path / "config"),
    )
    monkeypatch.setattr(tk, "_REGISTRY_CACHE", (None, {}))
    return repo


@pytest.fixture
def store(tmp_path: Path, config_dir: Path) -> kds.KnowledgeDraftStore:
    return kds.KnowledgeDraftStore(tmp_path / "calib_data")


def test_a_task_directory_is_stored_under_the_project_by_its_hash(
    store: kds.KnowledgeDraftStore, tmp_path: Path
) -> None:
    data = make_zip(RABI)

    draft = store.create("proj-1", data, filename="rabi.zip", uploaded_by="alice")

    assert draft.draft_id == hashlib.sha256(data).hexdigest()
    assert draft.task_name == "CheckRabi"
    assert (draft.filename, draft.uploaded_by) == ("rabi.zip", "alice")
    assert draft.warnings == []
    stored = tmp_path / "calib_data" / "projects" / "proj-1" / "knowledge-drafts" / draft.draft_id
    assert (stored / "draft.zip").read_bytes() == data
    assert (stored / "task" / "CheckRabi" / "index.md").is_file()
    assert [e.id for e in draft.knowledge.examples] == ["short"]
    assert draft.knowledge.reference().statuses["SUCCESS"] == "a damped cosine"
    # Figures resolve inside the draft, not the shared repository.
    loaded = draft.knowledge.load_figure_base64("examples/short.png")
    assert loaded == (base64.b64encode(PNG).decode("ascii"), "image/png")


def test_a_flat_zip_is_named_after_its_h1(store: kds.KnowledgeDraftStore) -> None:
    draft = store.create(
        "proj-1", make_zip({"index.md": INDEX}), filename="flat.zip", uploaded_by="alice"
    )

    assert draft.task_name == "CheckRabi"
    assert draft.warnings == []
    assert draft.knowledge.task_dir() is not None
    assert draft.knowledge.task_dir().name == "CheckRabi"  # type: ignore[union-attr]


def test_the_generators_warnings_are_kept(store: kds.KnowledgeDraftStore) -> None:
    draft = store.create(
        "proj-1", make_zip({"Rabi/index.md": INDEX}), filename="rabi.zip", uploaded_by="alice"
    )

    assert draft.task_name == "CheckRabi"
    assert draft.warnings == ["/Rabi: H1 'CheckRabi' differs from the directory name"]


def test_the_same_zip_is_the_same_draft(store: kds.KnowledgeDraftStore) -> None:
    data = make_zip(RABI)
    first = store.create("proj-1", data, filename="rabi.zip", uploaded_by="alice")

    again = store.create("proj-1", data, filename="copy.zip", uploaded_by="bob")

    assert again.draft_id == first.draft_id
    assert (again.filename, again.uploaded_by) == ("rabi.zip", "alice")
    assert store.get("proj-1", first.draft_id).task_name == "CheckRabi"


def test_drafts_are_scoped_to_their_project(store: kds.KnowledgeDraftStore) -> None:
    draft = store.create("proj-1", make_zip(RABI), filename="rabi.zip", uploaded_by="alice")

    with pytest.raises(HTTPException) as exc_info:
        store.get("proj-2", draft.draft_id)
    assert exc_info.value.status_code == 404
    with pytest.raises(HTTPException) as exc_info:
        store.get("proj-1", "../" + draft.draft_id)
    assert exc_info.value.status_code == 404


@pytest.mark.parametrize(
    ("data", "detail"),
    [
        (b"not a zip", "not a zip file"),
        (make_zip({"CheckRabi/index.md": INDEX, "../evil.md": "x"}), "inside the task directory"),
        (make_zip({"/abs/index.md": INDEX}), "inside the task directory"),
        (make_zip({"CheckRabi/index.md": INDEX, "CheckRabi/run.py": "x"}), "files are allowed"),
        (make_zip({"CheckRabi/index.md": INDEX}, links=("CheckRabi/link.md",)), "links"),
        (make_zip({"A/index.md": INDEX, "B/index.md": INDEX}), "one task directory"),
        (make_zip({"CheckRabi/notes.md": "x"}), "index.md is missing"),
        (make_zip({"index.md": "no title"}), "could not be read as task knowledge"),
    ],
)
def test_unusable_zips_are_rejected(
    store: kds.KnowledgeDraftStore, data: bytes, detail: str, tmp_path: Path
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        store.create("proj-1", data, filename="bad.zip", uploaded_by="alice")

    assert exc_info.value.status_code == 400
    assert detail in str(exc_info.value.detail)
    drafts_dir = tmp_path / "calib_data" / "projects" / "proj-1" / "knowledge-drafts"
    assert not drafts_dir.exists() or list(drafts_dir.iterdir()) == []


def test_archive_noise_is_ignored(store: kds.KnowledgeDraftStore) -> None:
    files: dict[str, bytes | str] = {
        **RABI,
        "__MACOSX/CheckRabi/._index.md": "x",
        "CheckRabi/.DS_Store": "x",
    }

    draft = store.create("proj-1", make_zip(files), filename="mac.zip", uploaded_by="alice")

    assert draft.task_name == "CheckRabi"


def test_size_limits_apply_to_the_zip_and_what_it_expands_to(
    store: kds.KnowledgeDraftStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = make_zip({"CheckRabi/index.md": INDEX + "x" * 4096})
    monkeypatch.setattr(kds, "MAX_ZIP_BYTES", len(data) - 1)
    with pytest.raises(HTTPException, match="exceeds"):
        store.create("proj-1", data, filename="big.zip", uploaded_by="alice")

    monkeypatch.setattr(kds, "MAX_ZIP_BYTES", 20 * 2**20)
    monkeypatch.setattr(kds, "MAX_EXTRACTED_BYTES", 1024)
    with pytest.raises(HTTPException, match="expands to more than"):
        store.create("proj-1", data, filename="big.zip", uploaded_by="alice")


def test_a_missing_generator_is_a_503(store: kds.KnowledgeDraftStore, config_dir: Path) -> None:
    (config_dir / "generate.py").unlink()

    with pytest.raises(HTTPException) as exc_info:
        store.create("proj-1", make_zip(RABI), filename="rabi.zip", uploaded_by="alice")

    assert exc_info.value.status_code == 503
