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
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets
from tests.qdash.workflow.task_call_helpers import (
    call_ids,
    effective_settings,
    names,
    settings,
)

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


def test_coherence_check_runs_expected_calls_in_one_step() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    assert len(result["steps"]) == 1
    (step,) = result["steps"]
    assert isinstance(step, CustomOneQubit)
    assert step.name == "coherence_check"
    assert step.execution_mode == "parallel_by_round"
    # The default per-target fail-fast policy applies to every call.
    assert step.continue_on_failure is False
    assert all(call.on_failure is None for call in step.tasks)
    assert names(step.tasks) == [
        "Configure",
        "CheckChevron",
        "CheckRabi",
        "CheckT1",
        "CheckT2Echo",
        "CheckRamsey",
        # The long Ramsey keeps its own Configure/Rabi measurement before it.
        "Configure",
        "CheckRabi",
        "CheckRamsey",
    ]


def test_coherence_check_gives_every_repeated_task_an_explicit_call_id() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    tasks = result["steps"][0].tasks
    assert call_ids(tasks) == [
        "configure_initial",
        "CheckChevron",
        "rabi_initial",
        "CheckT1",
        "CheckT2Echo",
        "ramsey_short",
        "configure_long_ramsey",
        "rabi_long_ramsey",
        "ramsey_long",
    ]
    repeated = {name for name in names(tasks) if names(tasks).count(name) > 1}
    assert repeated == {"Configure", "CheckRabi", "CheckRamsey"}
    assert all(call.call_id is not None for call in tasks if call.name in repeated)


def test_coherence_check_scales_long_ramsey_range_and_detuning_on_its_call() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    tasks = result["steps"][0].tasks
    short_ramsey = tasks[5]
    long_ramsey = tasks[-1]
    assert short_ramsey.call_id == "ramsey_short"
    assert long_ramsey.call_id == "ramsey_long"
    # Each Ramsey carries its own settings on its call.
    assert short_ramsey.effective_settings({}) == settings(
        run={"time_range": sweep.arange(0, 10_001, 100), "detuning": 0.001}
    )
    assert long_ramsey.effective_settings({}) == settings(
        # Keep 101 points while extending the time scale by 5x.
        run={"time_range": sweep.arange(0, 50_001, 500), "detuning": 0.0002}
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


def test_coherence_check_calls_carry_every_measurement_setting() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    # No per-task defaults: every setting is visible on the call it applies to.
    assert "task_parameters" not in result["kwargs"]
    (step,) = result["steps"]
    coherence_range = sweep.logspace(math.log10(300), math.log10(500_000), 51)
    assert effective_settings(step.tasks) == [
        ("configure_initial", settings()),
        (
            "CheckChevron",
            settings(
                run={
                    "detuning_range": sweep.linspace(-0.05, 0.05, 41),
                    "time_range": sweep.linspace(0, 250, 26),
                    "shots": 256,
                },
                update_calibration_parameters=False,
            ),
        ),
        ("rabi_initial", settings()),
        ("CheckT1", settings(run={"time_range": coherence_range})),
        ("CheckT2Echo", settings(run={"time_range": coherence_range})),
        (
            "ramsey_short",
            settings(run={"time_range": sweep.arange(0, 10_001, 100), "detuning": 0.001}),
        ),
        ("configure_long_ramsey", settings()),
        ("rabi_long_ramsey", settings()),
        (
            "ramsey_long",
            settings(run={"time_range": sweep.arange(0, 50_001, 500), "detuning": 0.0002}),
        ),
    ]


def test_coherence_check_chevron_settings_match_task_defaults() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    chevron = result["steps"][0].tasks[1]
    assert chevron.name == "CheckChevron"
    assert chevron.update_calibration_parameters is False
    for parameter_name in ("detuning_range", "time_range", "shots"):
        assert chevron.run is not None
        assert chevron.run[parameter_name]["value"] == CheckChevron.run_spec[parameter_name].default


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
