"""execution_mode on one-qubit steps, flow templates and strategies, with the deprecated aliases."""

from __future__ import annotations

import importlib
import warnings
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

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
    from qdash.workflow.service._internal.session import CalibSession

LEGACY = [
    ("synchronized", "parallel_by_round"),
    ("scheduled", "parallel_by_mux"),
    ("serial", "sequential"),
]
RABI = [TaskCall(name="CheckRabi")]


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------


def test_registry_uses_canonical_names_and_keeps_simultaneous_spectroscopy() -> None:
    assert {
        "parallel_by_round": strategy_module.OneQubitSynchronizedStrategy,
        "parallel_by_mux": strategy_module.OneQubitScheduledStrategy,
        "simultaneous_spectroscopy": strategy_module.OneQubitSimultaneousSpectroscopyStrategy,
        "sequential": strategy_module.OneQubitSerialStrategy,
    } == strategy_module.ONE_QUBIT_STRATEGIES


@pytest.mark.parametrize(("legacy", "canonical"), LEGACY)
def test_legacy_strategy_names_resolve_to_the_same_strategy(legacy: str, canonical: str) -> None:
    with pytest.warns(DeprecationWarning, match=f"execution_mode={canonical!r}"):
        old = strategy_module.get_one_qubit_strategy(legacy)
    new = strategy_module.get_one_qubit_strategy(canonical)
    assert type(old) is type(new) is strategy_module.ONE_QUBIT_STRATEGIES[canonical]


def test_unknown_strategy_name_raises() -> None:
    with pytest.raises(ValueError, match="Valid execution modes"):
        strategy_module.get_one_qubit_strategy("fast")


# ---------------------------------------------------------------------------
# Step classes
# ---------------------------------------------------------------------------


def test_step_defaults_are_unchanged() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert CustomOneQubit(tasks=RABI).execution_mode == "parallel_by_round"
        assert OneQubitCheck().execution_mode == "parallel_by_round"
        assert OneQubitFineTune().execution_mode == "parallel_by_round"
        assert BringUp().execution_mode == "parallel_by_mux"


@pytest.mark.parametrize(("legacy", "canonical"), LEGACY)
@pytest.mark.parametrize(
    "build",
    [
        lambda **kw: CustomOneQubit(tasks=RABI, **kw),
        lambda **kw: OneQubitCheck(tasks=RABI, **kw),
        lambda **kw: OneQubitFineTune(tasks=RABI, **kw),
        lambda **kw: BringUp(tasks=RABI, **kw),
    ],
    ids=["CustomOneQubit", "OneQubitCheck", "OneQubitFineTune", "BringUp"],
)
def test_legacy_mode_keyword_matches_canonical_execution_mode(
    build: Any, legacy: str, canonical: str
) -> None:
    with pytest.warns(DeprecationWarning, match=f"execution_mode={canonical!r} instead"):
        old = build(mode=legacy)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        new = build(execution_mode=canonical)
    assert old.execution_mode == new.execution_mode == canonical
    assert old.mode is None and new.mode is None
    assert old == new


@pytest.mark.parametrize(("legacy", "canonical"), LEGACY)
def test_legacy_value_name_in_execution_mode_is_accepted(legacy: str, canonical: str) -> None:
    with pytest.warns(DeprecationWarning, match="deprecated execution mode name"):
        step = OneQubitCheck(execution_mode=legacy)
    assert step.execution_mode == canonical


def test_positional_mode_slot_still_takes_a_legacy_value() -> None:
    with pytest.warns(DeprecationWarning):
        custom = CustomOneQubit("custom", RABI, "serial", True)
        check = OneQubitCheck("scheduled", RABI)
        bringup = BringUp("synchronized", RABI)
    assert (custom.execution_mode, custom.continue_on_failure) == ("sequential", True)
    assert check.execution_mode == "parallel_by_mux"
    assert bringup.execution_mode == "parallel_by_round"


def test_equivalent_explicit_values_are_accepted() -> None:
    with pytest.warns(DeprecationWarning, match="CustomOneQubit.mode='scheduled' is deprecated"):
        step = CustomOneQubit(tasks=RABI, execution_mode="parallel_by_mux", mode="scheduled")
    assert step.execution_mode == "parallel_by_mux"


@pytest.mark.parametrize(
    "build",
    [
        lambda: CustomOneQubit(tasks=RABI, execution_mode="parallel_by_mux", mode="serial"),
        lambda: OneQubitCheck(execution_mode="parallel_by_round", mode="scheduled"),
        lambda: OneQubitFineTune(execution_mode="sequential", mode="synchronized"),
        lambda: BringUp(execution_mode="parallel_by_mux", mode="serial"),
    ],
)
def test_conflicting_explicit_values_raise(build: Any) -> None:
    with pytest.raises(ValueError, match="conflicts with the deprecated"):
        build()


def test_a_legacy_mode_does_not_conflict_with_the_step_default() -> None:
    # BringUp defaults to parallel_by_mux; an explicit legacy "synchronized" wins.
    with pytest.warns(DeprecationWarning):
        assert BringUp(mode="synchronized").execution_mode == "parallel_by_round"


def test_parallel_by_round_connects_in_isolated_workers_only() -> None:
    assert CustomOneQubit(tasks=RABI).connect_parent_backend is False
    assert CustomOneQubit(tasks=RABI, execution_mode="parallel_by_mux").connect_parent_backend
    with pytest.warns(DeprecationWarning):
        assert CustomOneQubit(tasks=RABI, mode="synchronized").connect_parent_backend is False


@pytest.mark.parametrize(("legacy", "canonical"), [*LEGACY, ("simultaneous_spectroscopy",) * 2])
def test_execute_dispatches_the_canonical_strategy(
    monkeypatch: pytest.MonkeyPatch, legacy: str, canonical: str
) -> None:
    requested: list[str] = []

    class FakeStrategy:
        def execute(self, session: Any, config: Any) -> dict[str, Any]:
            return {}

    def fake_get(mode: str) -> FakeStrategy:
        requested.append(mode)
        return FakeStrategy()

    monkeypatch.setattr(strategy_module, "get_one_qubit_strategy", fake_get)
    logged: list[str] = []
    logger = SimpleNamespace(info=lambda *_: None, warning=logged.append)
    monkeypatch.setattr("qdash.workflow.service.steps.one_qubit.get_run_logger", lambda: logger)
    session = SimpleNamespace(chip_id="64Qv3", plan_digest=None)
    targets = MuxTargets(mux_ids=[0])

    with pytest.warns(DeprecationWarning):
        old = OneQubitCheck(tasks=RABI, mode=legacy)
    old.execute(cast("CalibSession", session), targets, StepContext())
    OneQubitCheck(tasks=RABI, execution_mode=canonical).execute(
        cast("CalibSession", session), targets, StepContext()
    )

    assert requested == [canonical, canonical]
    # The deprecation reaches the run log once, from the legacy step only.
    assert logged == [
        f"OneQubitCheck.mode={legacy!r} is deprecated and still accepted; "
        f"set OneQubitCheck.execution_mode={canonical!r} instead"
    ]


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


def _template(monkeypatch: pytest.MonkeyPatch, name: str) -> Any:
    module = importlib.import_module(f"qdash.workflow.templates.{name}")
    monkeypatch.setattr(module, "CalibService", FakeCalibService)
    if hasattr(module, "resolve_calib_context"):
        monkeypatch.setattr(module, "resolve_calib_context", lambda *a, **k: None)
    function_name, targets = TEMPLATES[name]
    flow = getattr(module, function_name)
    flow = getattr(flow, "fn", flow)

    def run(**kwargs: Any) -> str:
        steps = flow(username="alice", chip_id="64Q", **targets, **kwargs)
        return str(steps[0].execution_mode)

    return run


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_template_default_stays_parallel_by_mux(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    run = _template(monkeypatch, name)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert run() == "parallel_by_mux"
        assert run(execution_mode="parallel_by_round") == "parallel_by_round"


@pytest.mark.parametrize("name", sorted(TEMPLATES))
@pytest.mark.parametrize(("legacy", "canonical"), LEGACY)
def test_template_accepts_the_legacy_mode_parameter(
    monkeypatch: pytest.MonkeyPatch, name: str, legacy: str, canonical: str
) -> None:
    run = _template(monkeypatch, name)
    with pytest.warns(DeprecationWarning, match=f"set execution_mode={canonical!r}"):
        assert run(mode=legacy) == canonical
    with pytest.warns(DeprecationWarning):
        assert run(mode=legacy, execution_mode=canonical) == canonical


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_template_rejects_conflicting_mode_parameters(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    run = _template(monkeypatch, name)
    with pytest.raises(ValueError, match="conflicts with the deprecated mode='serial'"):
        run(mode="serial", execution_mode="parallel_by_mux")


def test_template_keeps_the_positional_slot_of_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("qdash.workflow.templates.simple")
    monkeypatch.setattr(module, "CalibService", FakeCalibService)
    # username, chip_id, mux_ids, exclude_qids, qids, tasks, then the former mode slot.
    with pytest.warns(DeprecationWarning):
        flow = getattr(module.simple_calibration, "fn", module.simple_calibration)
        steps = flow("alice", "64Q", [0], None, None, None, "serial")
    assert steps[0].execution_mode == "sequential"


def test_flow_source_saved_from_an_old_template_still_runs() -> None:
    """A user flow copied from a pre-rename template passes ``mode`` to the step."""
    source = """
from qdash.workflow import TaskCall
from qdash.workflow.service.steps import BringUp, CustomOneQubit

def old_flow(mode: str = "scheduled"):
    return [
        CustomOneQubit(step_name="simple_tasks", tasks=[TaskCall(name="CheckRabi")], mode=mode),
        BringUp(mode=mode),
    ]
"""
    namespace: dict[str, Any] = {}
    exec(compile(source, "<saved-flow>", "exec"), namespace)  # noqa: S102 - fixed test source
    with pytest.warns(DeprecationWarning):
        custom, bringup = namespace["old_flow"]()
    assert custom.execution_mode == bringup.execution_mode == "parallel_by_mux"
    with pytest.warns(DeprecationWarning):
        custom, _ = namespace["old_flow"](mode="synchronized")
    assert custom.execution_mode == "parallel_by_round"
