"""Verify the coherence check template task order and execution policy."""

from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from qdash.workflow import sweep
from qdash.workflow.calibtasks.qubex import CheckChevron
from qdash.workflow.engine.task_parameters import normalize_task_parameters
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets

coherence_check_module = importlib.import_module("qdash.workflow.templates.coherence_check")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "args": self.args, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coherence_check_module, "CalibService", FakeCalibService)


def test_coherence_check_runs_expected_tasks_in_order() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    assert len(result["steps"]) == 2
    first_step, second_step = result["steps"]
    assert isinstance(first_step, CustomOneQubit)
    assert first_step.name == "coherence_check"
    assert first_step.mode == "synchronized"
    assert first_step.tasks == [
        "Configure",
        "CheckChevron",
        "CheckRabi",
        "CheckT1",
        "CheckT2Echo",
        "CheckRamsey",
    ]
    assert isinstance(second_step, CustomOneQubit)
    assert second_step.name == "long_ramsey_check"
    assert second_step.mode == "synchronized"
    assert second_step.tasks == ["Configure", "CheckRabi", "CheckRamsey"]


def test_coherence_check_scales_second_ramsey_range_and_detuning() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    settings = normalize_task_parameters(result["steps"][1].task_parameters)["CheckRamsey"]
    assert settings["run"]["time_range"] == {
        "value": (0, 50_001, 500),
        "value_type": "np.arange",
    }
    assert settings["run"]["detuning"] == {"value": 0.0002}


def test_coherence_check_uses_explicit_task_settings() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    assert result["kwargs"]["task_parameters"] == {
        "CheckChevron": {
            "run": {
                "detuning_range": sweep.linspace(-0.05, 0.05, 41),
                "time_range": sweep.linspace(0, 250, 26),
                "shots": 256,
            },
            "update_calibration_parameters": False,
        },
        "CheckT1": {
            "run": {
                "time_range": sweep.logspace(
                    math.log10(300),
                    math.log10(500_000),
                    51,
                ),
            },
        },
        "CheckT2Echo": {
            "run": {
                "time_range": sweep.logspace(
                    math.log10(300),
                    math.log10(500_000),
                    51,
                ),
            },
        },
        "CheckRamsey": {
            "run": {
                "time_range": sweep.arange(0, 10_001, 100),
                "detuning": 0.001,
            },
        },
    }
    chevron_settings = normalize_task_parameters(result["kwargs"]["task_parameters"])[
        "CheckChevron"
    ]
    for parameter_name in ("detuning_range", "time_range", "shots"):
        assert (
            chevron_settings["run"][parameter_name]["value"]
            == CheckChevron.run_spec[parameter_name].default
        )


def test_coherence_check_uses_explicit_shared_run_defaults() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    assert result["kwargs"]["default_run_parameters"] == {
        "readout_duration": 1024,
        "interval": 256 * 1024,
    }


def test_coherence_check_uses_explicit_qubits() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    assert isinstance(result["targets"], QubitTargets)
    assert result["targets"].qids == ["0", "1"]


def test_coherence_check_prefers_mux_targets_and_preserves_exclusions() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        mux_ids=[0, 1],
        exclude_qids=["2"],
        qids=["8"],
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0, 1]
    assert result["targets"].exclude_qids == ["2"]


def test_coherence_check_requires_explicit_targets() -> None:
    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        coherence_check_module.coherence_check(username="alice", chip_id="64Q")


def test_coherence_check_is_listed_as_a_template() -> None:
    module_file = coherence_check_module.__file__
    assert module_file is not None
    metadata_path = Path(module_file).with_name("templates.json")
    templates = json.loads(metadata_path.read_text())

    assert any(
        template["id"] == "coherence_check"
        and template["filename"] == "coherence_check.py"
        and template["function_name"] == "coherence_check"
        for template in templates
    )
