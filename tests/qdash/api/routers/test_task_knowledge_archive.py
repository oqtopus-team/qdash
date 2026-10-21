"""Tests for downloading a task's knowledge directory as a zip."""

from __future__ import annotations

import io
import json
import zipfile
from typing import TYPE_CHECKING

import pytest

from qdash.datamodel import task_knowledge as tk
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi.testclient import TestClient


@pytest.fixture
def headers(init_db: object) -> dict[str, str]:
    UserDocument(
        username="alice",
        hashed_password="hashed",
        access_token="alice-token",
        system_info=SystemInfoModel(),
    ).insert()
    return {"Authorization": "Bearer alice-token"}


@pytest.fixture
def knowledge_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A knowledge checkout holding CheckRabi's directory and its generated JSON."""
    repo = tmp_path / "task-knowledge"
    task_dir = repo / "one_qubit_coarse" / "CheckRabi"
    task_dir.mkdir(parents=True)
    (task_dir / "index.md").write_text("# CheckRabi\n\nRabi oscillation.\n", encoding="utf-8")
    (task_dir / "expected.png").write_bytes(b"\x89PNG-rabi")
    (repo / "task-knowledge.json").write_text(
        json.dumps(
            {
                "CheckRabi": {
                    "name": "CheckRabi",
                    "category": "one_qubit_coarse",
                    "background": "Rabi oscillation.",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "qdash.common.config.loader.ConfigLoader.get_config_dir", classmethod(lambda cls: tmp_path)
    )
    monkeypatch.setattr(tk, "_REGISTRY_CACHE", (None, {}))
    return repo


def test_the_task_directory_downloads_as_a_zip(
    test_client: TestClient, headers: dict[str, str], knowledge_repo: Path
) -> None:
    response = test_client.get("/tasks/CheckRabi/knowledge/archive", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="CheckRabi.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == ["CheckRabi/expected.png", "CheckRabi/index.md"]
        assert archive.read("CheckRabi/expected.png") == b"\x89PNG-rabi"


def test_a_task_without_knowledge_has_no_archive(
    test_client: TestClient, headers: dict[str, str], knowledge_repo: Path
) -> None:
    response = test_client.get("/tasks/CheckT1/knowledge/archive", headers=headers)

    assert response.status_code == 404


def test_the_archive_requires_a_signed_in_user(
    test_client: TestClient, knowledge_repo: Path
) -> None:
    response = test_client.get("/tasks/CheckRabi/knowledge/archive")

    assert response.status_code in {401, 403}
