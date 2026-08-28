"""Tests for calibration directory creation."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from qdash.workflow.engine.orchestrator import CalibOrchestrator


def test_create_directories_creates_classifier_parents(tmp_path: Path) -> None:
    """A project's first classifier directory creates the full shared path."""
    orchestrator = object.__new__(CalibOrchestrator)
    orchestrator.config = cast(
        "Any",
        SimpleNamespace(
            calib_data_path=str(tmp_path / "executions" / "exec-1"),
            classifier_dir=str(tmp_path / "shared" / "classifier"),
        ),
    )

    orchestrator._create_directories()

    assert (tmp_path / "shared" / "classifier").is_dir()
