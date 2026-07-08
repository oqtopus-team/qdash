from __future__ import annotations

import importlib
from typing import Any

from qdash.workflow.service.targets import MuxTargets, QubitTargets

one_qubit_module = importlib.import_module("qdash.workflow.templates.one_qubit")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps}


def test_one_qubit_template_uses_explicit_qids(monkeypatch) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    assert isinstance(result["targets"], QubitTargets)
    assert result["targets"].qids == ["0", "1"]


def test_one_qubit_template_prefers_mux_ids(monkeypatch) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(
        username="alice",
        chip_id="64Q",
        mux_ids=[0],
        qids=["8"],
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0]


def test_one_qubit_template_defaults_to_all_muxes(monkeypatch) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(username="alice", chip_id="64Q")

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == list(range(16))
