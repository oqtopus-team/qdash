from __future__ import annotations

import importlib
from typing import Any

check_waveform_module = importlib.import_module("qdash.workflow.templates.check_waveform")


class FakeCalibService:
    last_kwargs: dict[str, Any] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        FakeCalibService.last_kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps}


def test_check_waveform_template_runs_check_waveform_step(monkeypatch) -> None:
    monkeypatch.setattr(check_waveform_module, "CalibService", FakeCalibService)

    result = check_waveform_module.check_waveform(
        username="alice",
        chip_id="16Q-test",
        mux_ids=[0],
    )

    step = result["steps"][0]
    assert step.name == "check_waveform"
    assert step.tasks == ["CheckWaveform"]
    assert step.mode == "scheduled"


def test_check_waveform_template_sets_default_interval(monkeypatch) -> None:
    monkeypatch.setattr(check_waveform_module, "CalibService", FakeCalibService)

    check_waveform_module.check_waveform(
        username="alice",
        chip_id="16Q-test",
        qids=["0"],
    )

    assert FakeCalibService.last_kwargs is not None
    assert FakeCalibService.last_kwargs["default_run_parameters"] == {
        "interval": {"value": 150 * 1024, "value_type": "int"},
    }
