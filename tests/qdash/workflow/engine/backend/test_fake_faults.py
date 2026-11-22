"""Opt-in validation faults of the fake backend."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.backend.fake_faults import (
    FAULT_INJECTION_ENV,
    MAX_FAULT_LIFETIME,
    FakeValidationFault,
    fault_file_path,
    load_fault,
    raise_validation_fault,
)
from qdash.workflow.engine.backend.qubex_paths import QubexPaths
from qdash.workflow.engine.task.executor import TaskExecutor

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
ENABLED = {FAULT_INJECTION_ENV: "1"}


def write_fault(chip_dir: Path, **overrides: Any) -> Path:
    data: dict[str, Any] = {
        "fault_id": "fault-1",
        "chip_id": "val-chip",
        "qid": "4",
        "task_name": "CheckT1",
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
    }
    data.update(overrides)
    path = fault_file_path(chip_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def fire(
    chip_dir: Path, *, env: dict[str, str] = ENABLED, task: str = "CheckT1", qid: str = "4"
) -> None:
    raise_validation_fault(
        chip_dir=chip_dir, chip_id="val-chip", task_name=task, qid=qid, env=env, now=NOW
    )


def test_matching_fault_fails_the_run_and_names_itself(tmp_path: Path) -> None:
    write_fault(tmp_path)
    with pytest.raises(FakeValidationFault, match="validation fault fault-1") as caught:
        fire(tmp_path)
    assert "injected" in str(caught.value)


def test_no_fault_without_opt_in_environment(tmp_path: Path) -> None:
    write_fault(tmp_path)
    fire(tmp_path, env={})
    fire(tmp_path, env={FAULT_INJECTION_ENV: "true"})


@pytest.mark.parametrize(("task", "qid"), [("CheckRabi", "4"), ("CheckT1", "5")])
def test_fault_only_fails_the_named_task_and_qubit(tmp_path: Path, task: str, qid: str) -> None:
    write_fault(tmp_path)
    fire(tmp_path, task=task, qid=qid)


def test_fault_for_another_chip_does_not_fire(tmp_path: Path) -> None:
    write_fault(tmp_path, chip_id="other-chip")
    fire(tmp_path)


@pytest.mark.parametrize(
    "expires_at",
    [
        (NOW - timedelta(seconds=1)).isoformat(),
        (NOW + MAX_FAULT_LIFETIME + timedelta(seconds=1)).isoformat(),
        "2026-11-22T12:10:00",  # no time zone
        "soon",
        3600,
    ],
)
def test_stale_unbounded_or_malformed_expiry_disables_the_fault(
    tmp_path: Path, expires_at: object
) -> None:
    write_fault(tmp_path, expires_at=expires_at)
    assert load_fault(tmp_path, env=ENABLED, now=NOW) is None
    fire(tmp_path)


def test_malformed_file_disables_the_fault(tmp_path: Path) -> None:
    path = fault_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    fire(tmp_path)
    path.write_text(json.dumps(["CheckT1"]), encoding="utf-8")
    fire(tmp_path)
    write_fault(tmp_path, qid=4)
    fire(tmp_path)


def test_missing_file_is_no_fault(tmp_path: Path) -> None:
    assert load_fault(tmp_path, env=ENABLED, now=NOW) is None


def test_fake_backend_reads_the_fault_of_its_chip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = QubexPaths(config_base=tmp_path)
    monkeypatch.setattr("qdash.workflow.engine.backend.fake.get_qubex_paths", lambda: paths)
    monkeypatch.setenv(FAULT_INJECTION_ENV, "1")
    write_fault(
        paths.chip_dir("val-chip"),
        expires_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    )
    backend = FakeBackend({"chip_id": "val-chip"})
    backend.before_task_run("CheckRabi", "4")
    with pytest.raises(FakeValidationFault):
        backend.before_task_run("CheckT1", "4")
    FakeBackend({"chip_id": "another"}).before_task_run("CheckT1", "4")


def test_base_backend_hook_is_a_no_op() -> None:
    BaseBackend.before_task_run(object(), "CheckT1", "4")  # type: ignore[arg-type]


class _Task:
    def __init__(self) -> None:
        self.ran = False

    def get_name(self) -> str:
        return "CheckT1"

    def run(self, backend: object, qid: str) -> None:
        self.ran = True


class _RefusingBackend:
    name = "fake"

    def before_task_run(self, task_name: str, qid: str) -> None:
        raise FakeValidationFault(f"{task_name}:{qid}")


class _PlainBackend:
    name = "qubex"


def test_executor_asks_the_backend_before_the_task_measures() -> None:
    executor = TaskExecutor.__new__(TaskExecutor)
    task = _Task()
    with pytest.raises(FakeValidationFault, match="CheckT1:4"):
        executor._run_task(task, _RefusingBackend(), "4")  # type: ignore[arg-type]
    assert task.ran is False
    executor._run_task(task, _PlainBackend(), "4")  # type: ignore[arg-type]
    assert task.ran is True
