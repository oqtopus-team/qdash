"""execution_mode on one-qubit steps, flow templates and strategies."""

from __future__ import annotations

import importlib
import inspect
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast, get_type_hints

import pytest
from pydantic import TypeAdapter, ValidationError

from qdash.datamodel.one_qubit_execution_mode import ONE_QUBIT_EXECUTION_MODES
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service import strategy as strategy_module
from qdash.workflow.service.steps import (
    BringUp,
    CustomOneQubit,
    OneQubitCheck,
    OneQubitFineTune,
)
from qdash.workflow.service.steps.pipeline import StepContext
from qdash.workflow.service.targets import MuxTargets

if TYPE_CHECKING:
    from qdash.datamodel.one_qubit_execution_mode import OneQubitExecutionMode
    from qdash.workflow.service._internal.session import CalibSession

# Names used before the rename; they are no longer accepted anywhere.
REMOVED = ["synchronized", "scheduled", "serial"]
RABI = [TaskCall(name="CheckRabi")]

STEP_BUILDERS = [
    lambda **kw: CustomOneQubit(tasks=RABI, **kw),
    lambda **kw: OneQubitCheck(tasks=RABI, **kw),
    lambda **kw: OneQubitFineTune(tasks=RABI, **kw),
    lambda **kw: BringUp(tasks=RABI, **kw),
]
STEP_IDS = ["CustomOneQubit", "OneQubitCheck", "OneQubitFineTune", "BringUp"]


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------


def test_registry_maps_every_execution_mode_to_its_strategy() -> None:
    assert {
        "parallel_by_round": strategy_module.OneQubitParallelByRoundStrategy,
        "parallel_by_mux": strategy_module.OneQubitParallelByMuxStrategy,
        "simultaneous_spectroscopy": strategy_module.OneQubitSimultaneousSpectroscopyStrategy,
        "sequential": strategy_module.OneQubitSequentialStrategy,
    } == strategy_module.ONE_QUBIT_STRATEGIES
    assert set(strategy_module.ONE_QUBIT_STRATEGIES) == set(ONE_QUBIT_EXECUTION_MODES)


@pytest.mark.parametrize("mode", ONE_QUBIT_EXECUTION_MODES)
def test_get_strategy_returns_the_registered_strategy(mode: str) -> None:
    strategy = strategy_module.get_one_qubit_strategy(mode)
    assert type(strategy) is strategy_module.ONE_QUBIT_STRATEGIES[mode]  # type: ignore[index]


@pytest.mark.parametrize("value", [*REMOVED, "fast"])
def test_get_strategy_rejects_removed_and_unknown_names(value: str) -> None:
    with pytest.raises(ValueError, match="Valid execution modes"):
        strategy_module.get_one_qubit_strategy(value)


# ---------------------------------------------------------------------------
# Step classes
# ---------------------------------------------------------------------------


def test_step_defaults_are_unchanged() -> None:
    assert CustomOneQubit(tasks=RABI).execution_mode == "parallel_by_round"
    assert OneQubitCheck().execution_mode == "parallel_by_round"
    assert OneQubitFineTune().execution_mode == "parallel_by_round"
    assert BringUp().execution_mode == "parallel_by_mux"


@pytest.mark.parametrize("mode", ONE_QUBIT_EXECUTION_MODES)
@pytest.mark.parametrize("build", STEP_BUILDERS, ids=STEP_IDS)
def test_steps_accept_every_canonical_mode(build: Any, mode: str) -> None:
    assert build(execution_mode=mode).execution_mode == mode


@pytest.mark.parametrize("value", [*REMOVED, "fast"])
@pytest.mark.parametrize("build", STEP_BUILDERS, ids=STEP_IDS)
def test_steps_reject_removed_and_unknown_names(build: Any, value: str) -> None:
    with pytest.raises(ValueError, match=f"Unknown execution_mode {value!r}"):
        build(execution_mode=value)


@pytest.mark.parametrize("build", STEP_BUILDERS, ids=STEP_IDS)
def test_steps_no_longer_take_a_mode_keyword(build: Any) -> None:
    with pytest.raises(TypeError, match="mode"):
        build(mode="parallel_by_mux")


def test_parallel_by_round_connects_in_isolated_workers_only() -> None:
    assert CustomOneQubit(tasks=RABI).connect_parent_backend is False
    assert CustomOneQubit(tasks=RABI, execution_mode="parallel_by_mux").connect_parent_backend
    assert CustomOneQubit(tasks=RABI, execution_mode="sequential").connect_parent_backend


@pytest.mark.parametrize("mode", ONE_QUBIT_EXECUTION_MODES)
def test_execute_dispatches_the_strategy_of_its_mode(
    monkeypatch: pytest.MonkeyPatch, mode: OneQubitExecutionMode
) -> None:
    requested: list[str] = []

    class FakeStrategy:
        def execute(self, session: Any, config: Any) -> dict[str, Any]:
            return {}

    def fake_get(execution_mode: str) -> FakeStrategy:
        requested.append(execution_mode)
        return FakeStrategy()

    monkeypatch.setattr(strategy_module, "get_one_qubit_strategy", fake_get)
    logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)
    monkeypatch.setattr("qdash.workflow.service.steps.one_qubit.get_run_logger", lambda: logger)
    session = SimpleNamespace(chip_id="64Qv3", plan_digest=None)

    OneQubitCheck(tasks=RABI, execution_mode=mode).execute(
        cast("CalibSession", session), MuxTargets(mux_ids=[0]), StepContext()
    )

    assert requested == [mode]


# ---------------------------------------------------------------------------
# Flow templates
# ---------------------------------------------------------------------------

TEMPLATES = {
    "simple": ("simple_calibration", {"mux_ids": [0]}),
    "check_waveform": ("check_waveform", {"mux_ids": [0]}),
    "coherence_limit": ("coherence_limit", {"mux_ids": [0]}),
    "fake_backend": ("fake_calibration", {"mux_ids": [0]}),
    "bringup": ("bringup", {"mux_ids": [0]}),
    "box_setup": ("box_setup", {"mux_ids": [0]}),
}


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    @classmethod
    def from_context(cls, *args: Any, **kwargs: Any) -> FakeCalibService:
        return cls()

    def run(self, targets: Any, *, steps: list[Any]) -> list[Any]:
        return steps


def _flow(monkeypatch: pytest.MonkeyPatch, name: str) -> Any:
    module = importlib.import_module(f"qdash.workflow.templates.{name}")
    monkeypatch.setattr(module, "CalibService", FakeCalibService)
    if hasattr(module, "resolve_calib_context"):
        monkeypatch.setattr(module, "resolve_calib_context", lambda *a, **k: None)
    return getattr(module, TEMPLATES[name][0])


def _template(monkeypatch: pytest.MonkeyPatch, name: str) -> Any:
    flow = _flow(monkeypatch, name)
    fn = getattr(flow, "fn", flow)

    def run(**kwargs: Any) -> str:
        steps = fn(username="alice", chip_id="64Q", **TEMPLATES[name][1], **kwargs)
        return str(steps[0].execution_mode)

    return run


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_template_default_stays_parallel_by_mux(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    run = _template(monkeypatch, name)
    assert run() == "parallel_by_mux"
    assert run(execution_mode="parallel_by_round") == "parallel_by_round"
    assert run(execution_mode="sequential") == "sequential"


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_template_rejects_removed_names_and_the_mode_parameter(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    run = _template(monkeypatch, name)
    with pytest.raises(ValueError, match="Unknown execution_mode 'scheduled'"):
        run(execution_mode="scheduled")
    with pytest.raises(TypeError, match="mode"):
        run(mode="parallel_by_mux")


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_flow_run_parameter_type_rejects_removed_names(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Flow-run parameters are validated against the execution_mode annotation.

    Prefect builds a Pydantic model from the flow signature; Prefect itself is
    mocked in these tests, so validate the annotation directly.
    """
    flow = _flow(monkeypatch, name)
    fn = getattr(flow, "fn", flow)
    parameters = inspect.signature(fn).parameters
    assert "mode" not in parameters
    assert parameters["execution_mode"].default == "parallel_by_mux"
    adapter = TypeAdapter(get_type_hints(fn)["execution_mode"])
    for mode in ONE_QUBIT_EXECUTION_MODES:
        assert adapter.validate_python(mode) == mode
    for old in REMOVED:
        with pytest.raises(ValidationError):
            adapter.validate_python(old)
