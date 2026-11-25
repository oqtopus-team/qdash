"""The workflow ``CalibrationSession``, ``calibration_flow`` and the definition conversion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from qdash.calibration import (
    CalibrationResult,
    CouplingTargets,
    CustomOneQubit,
    CustomTwoQubit,
    FilterByMetric,
    MuxTargets,
    OneQubitCheck,
    QubitTargets,
    TaskCall,
    TwoQubitCalibration,
    sweep,
)
from qdash.repository.run_ledger import NOTE_RUN_KEY, NOTE_SESSION_KEY
from qdash.workflow import CalibrationSession, calibration_flow
from qdash.workflow.service import steps as runtime
from qdash.workflow.service import targets as runtime_targets
from qdash.workflow.service._internal.lifecycle import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.calibration_flow import SESSION_NAME_ATTRIBUTE, session_name_of
from qdash.workflow.service.definitions import runtime_steps, runtime_target
from qdash.workflow.service.steps.base import TransformStep
from tests.qdash.workflow.context_helpers import granted_context


@dataclass
class FakeRuntime:
    run_identity: dict[str, str] = field(default_factory=dict)
    run_execution_ids: list[str] = field(default_factory=list)


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record each run handed to the owner runtime; every run is in one flow run."""
    recorded: list[dict[str, Any]] = []

    def run_calibration_with_runtime(
        settings: Any, targets: Any, steps: Any
    ) -> tuple[dict[str, Any], FakeRuntime]:
        recorded.append({"settings": settings, "targets": targets, "steps": steps})
        index = len(recorded)
        runtime = FakeRuntime(
            {NOTE_SESSION_KEY: "cs-auto-1", NOTE_RUN_KEY: "cpr-1"}, [f"exec-{index}"]
        )
        return {
            "candidate_qids": ["0", "1"],
            "candidate_couplings": [],
            "steps": {"rabi": {"typed": index}},
        }, runtime

    monkeypatch.setattr(
        "qdash.workflow.service._internal.runs.run_calibration_with_runtime",
        run_calibration_with_runtime,
    )
    monkeypatch.setattr(
        "qdash.workflow.service._internal.runs.load_flow_default_run_parameters",
        lambda project_id, flow_name: {},
    )
    return recorded


def _session() -> CalibrationSession:
    return CalibrationSession.from_context(granted_context(project_id="project-1"))


def test_a_session_comes_only_from_a_checked_context() -> None:
    with pytest.raises(TypeError, match="from_context"):
        CalibrationSession(granted_context())
    with pytest.raises(TypeError, match="resolve_calib_context"):
        CalibrationSession.from_context(object())  # type: ignore[arg-type]


def test_runs_share_the_launch_membership_and_return_the_common_result(
    runs: list[dict[str, Any]],
) -> None:
    session = _session()
    before = (session.calibration_session_id, session.run_id)
    assert before == (None, None)
    steps = [CustomOneQubit(step_name="rabi", tasks=[TaskCall(name="CheckRabi")])]

    first = session.run(targets=QubitTargets(["0", "1"]), steps=steps, name="nightly")
    second = session.run(QubitTargets(["0", "1"]), steps, name="nightly")

    for index, result in enumerate((first, second), start=1):
        assert isinstance(result, CalibrationResult)
        assert result.status == "completed" and result.succeeded
        assert (result.calibration_session_id, result.run_id) == ("cs-auto-1", "cpr-1")
        assert result.execution_ids == (f"exec-{index}",)
        assert result.candidate_qids == ("0", "1")
        # The typed per-step data is kept, not flattened.
        assert result.steps == {"rabi": {"typed": index}}
    assert (session.calibration_session_id, session.run_id) == ("cs-auto-1", "cpr-1")
    [step] = runs[0]["steps"]
    assert isinstance(step, runtime.CustomOneQubit)
    assert isinstance(runs[0]["targets"], runtime_targets.QubitTargets)
    assert runs[0]["settings"].flow_name == "nightly"


def test_run_defaults_are_normalized_and_left_to_the_saved_flow_when_absent(
    runs: list[dict[str, Any]],
) -> None:
    steps = [CustomOneQubit(tasks=[TaskCall(name="CheckRabi")])]
    _session().run(
        QubitTargets(["0"]),
        steps,
        default_run_parameters={"shots": 128, "time_range": sweep.linspace(0, 1, 3)},
        tags=["t"],
        note={"why": "test"},
    )
    _session().run(QubitTargets(["0"]), steps)

    settings = runs[0]["settings"]
    assert settings.default_run_parameters == {
        "shots": {"value": 128},
        "time_range": {"value": (0, 1, 3), "value_type": "np.linspace"},
    }
    assert (settings.tags, settings.note) == (["t"], {"why": "test"})
    assert runs[1]["settings"].default_run_parameters == {}


def test_a_failing_run_raises_its_own_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    class StepFailedError(RuntimeError):
        pass

    def fail(*_: Any) -> Any:
        raise StepFailedError("CheckRabi failed on qubit 0")

    monkeypatch.setattr("qdash.workflow.service._internal.runs.run_calibration_with_runtime", fail)
    monkeypatch.setattr(
        "qdash.workflow.service._internal.runs.load_flow_default_run_parameters",
        lambda project_id, flow_name: {},
    )
    with pytest.raises(StepFailedError, match="CheckRabi failed"):
        _session().run(QubitTargets(["0"]), [CustomOneQubit(tasks=[TaskCall(name="CheckRabi")])])


def test_custom_runtime_steps_run_beside_definitions(runs: list[dict[str, Any]]) -> None:
    @dataclass
    class KeepFirst(TransformStep):
        @property
        def name(self) -> str:
            return "keep_first"

        def execute(self, session: Any, targets: Any, ctx: Any) -> Any:
            ctx.candidate_qids = ctx.candidate_qids[:1]
            return ctx

    custom = KeepFirst()
    _session().run(
        MuxTargets([0]),
        [OneQubitCheck(), custom, FilterByMetric(metric="t1_average", threshold=30.0)],
    )
    built = runs[0]["steps"]
    assert isinstance(built[0], runtime.OneQubitCheck)
    assert built[1] is custom
    assert isinstance(built[2], runtime.FilterByMetric)


def test_validate_reports_problems_without_running(runs: list[dict[str, Any]]) -> None:
    session = _session()
    valid = session.validate(
        QubitTargets(["0"]), [CustomOneQubit(step_name="a", tasks=[TaskCall(name="CheckRabi")])]
    )
    assert valid.valid and valid.problems == ()
    repeated = session.validate(
        QubitTargets(["0"]),
        [
            CustomOneQubit(step_name="a", tasks=[TaskCall(name="CheckRabi")]),
            CustomOneQubit(step_name="a", tasks=[TaskCall(name="CheckRabi")]),
        ],
    )
    assert not repeated.valid and "step_id 'a'" in repeated.problems[0]
    duplicate_calls = session.validate(
        QubitTargets(["0"]),
        [CustomOneQubit(tasks=[TaskCall(name="CheckRabi"), TaskCall(name="CheckRabi")])],
    )
    assert not duplicate_calls.valid and "call_id" in duplicate_calls.problems[0]
    assert runs == []


def test_two_qubit_definitions_keep_modes_rounds_and_direction() -> None:
    target = runtime_target(CouplingTargets([("1", "0"), ("4", "5")]))
    assert isinstance(target, runtime_targets.CouplingTargets)
    assert target.pairs == [("1", "0"), ("4", "5")]

    manual, automatic, custom = cast(
        "list[Any]",
        runtime_steps(
            [
                TwoQubitCalibration(execution_mode="manual", rounds=[[("1", "0")], [("4", "5")]]),
                TwoQubitCalibration(max_parallel_ops=3),
                CustomTwoQubit(tasks=[TaskCall(name="CheckCrossResonance")]),
            ]
        ),
    )
    assert (manual.execution_mode, manual.rounds) == ("manual", [[("1", "0")], [("4", "5")]])
    assert manual.max_parallel_ops is None
    assert (automatic.execution_mode, automatic.max_parallel_ops) == ("automatic", 3)
    assert (custom.execution_mode, custom.max_parallel_ops, custom.name) == (
        "automatic",
        None,
        "custom_two_qubit",
    )
    with pytest.raises(ValueError, match="max_parallel_ops"):
        TwoQubitCalibration(execution_mode="manual", rounds=[[("0", "1")]], max_parallel_ops=2)


def test_calibration_flow_sets_qdash_hooks_and_the_session_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []

    def fake_flow(**options: Any) -> Any:
        captured.append(options)
        return lambda function: function

    monkeypatch.setattr("prefect.flow", fake_flow)

    @calibration_flow(session_name="  Coherence Check ")
    def named(username: str, chip_id: str) -> None:
        return None

    @calibration_flow
    def unnamed(username: str, chip_id: str) -> None:
        return None

    def own_hook(*_: Any) -> None:
        return None

    @calibration_flow(session_name="X", on_failure=[own_hook], retries=1)
    def custom(username: str, chip_id: str) -> None:
        return None

    assert session_name_of(named) == "Coherence Check"
    assert getattr(unnamed, SESSION_NAME_ATTRIBUTE) is None and session_name_of(unnamed) is None
    assert captured[0] == {
        "on_cancellation": [on_flow_cancellation],
        "on_failure": [on_flow_failure],
        "on_crashed": [on_flow_crashed],
    }
    assert captured[2]["on_failure"] == [own_hook] and captured[2]["retries"] == 1
    assert captured[2]["on_crashed"] == [on_flow_crashed]
    for bad in ("", "   ", "x" * 501):
        with pytest.raises(ValueError, match="session_name"):
            calibration_flow(session_name=bad)
    with pytest.raises(TypeError, match="session_name"):
        calibration_flow(session_name=cast("str", 3))


# --- Run name and saved defaults from the launch ---------------------------------------------


@pytest.fixture
def saved_defaults(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Record the saved flow each run reads defaults from; only "Nightly" has any."""
    lookups: list[str | None] = []

    def load(project_id: str, flow_name: str | None) -> dict[str, Any]:
        lookups.append(flow_name)
        return {"interval": {"value": 7}} if flow_name == "Nightly" else {}

    monkeypatch.setattr(
        "qdash.workflow.service._internal.runs.load_flow_default_run_parameters", load
    )
    return lookups


def _in_flow_run(
    monkeypatch: pytest.MonkeyPatch,
    parameters: dict[str, Any] | None,
    *,
    prefect_flow_name: str = "nightly-calibration",
) -> None:
    """Run inside a Prefect flow run with these parameters and this Prefect flow name."""
    import sys
    from types import SimpleNamespace

    flow_run = SimpleNamespace(id="flow-run-1", parameters=parameters or {})
    context = SimpleNamespace(flow_run=flow_run, flow=SimpleNamespace(name=prefect_flow_name))
    monkeypatch.setitem(
        sys.modules,
        "prefect.context",
        SimpleNamespace(
            FlowRunContext=SimpleNamespace(get=lambda: context),
            get_run_context=lambda: context,
        ),
    )


def _outside_flow_run(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace

    def no_context() -> Any:
        raise RuntimeError("no run context")

    monkeypatch.setitem(
        sys.modules,
        "prefect.context",
        SimpleNamespace(
            FlowRunContext=SimpleNamespace(get=lambda: None), get_run_context=no_context
        ),
    )


STEPS = [CustomOneQubit(step_name="rabi", tasks=[TaskCall(name="CheckRabi")])]


def test_a_qdash_launch_names_the_run_and_reads_defaults_from_its_saved_flow(
    runs: list[dict[str, Any]],
    saved_defaults: list[str | None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _in_flow_run(monkeypatch, {"flow_name": "Nightly", "source_execution_id": "exec-src"})

    _session().run(QubitTargets(["0"]), STEPS)

    settings = runs[0]["settings"]
    assert settings.flow_name == "Nightly"
    assert saved_defaults == ["Nightly"]
    assert settings.default_run_parameters == {"interval": {"value": 7}}
    # Naming adds no metadata and leaves the snapshot source as it was.
    assert (settings.tags, settings.note) == (None, None)
    assert settings.snapshot.execution_id == "exec-src"
    # The steps keep their own names; the run name only prefixes their Executions.
    [step] = runs[0]["steps"]
    assert step.name == "rabi"


def test_an_explicit_name_overrides_the_display_name_only(
    runs: list[dict[str, Any]],
    saved_defaults: list[str | None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _in_flow_run(monkeypatch, {"flow_name": "Nightly"})

    _session().run(QubitTargets(["0"]), STEPS, name="nightly-manual")
    # A legacy flow forwarding the injected flow_name behaves as the omitted name.
    _session().run(QubitTargets(["0"]), STEPS, name="Nightly")

    assert [run["settings"].flow_name for run in runs] == ["nightly-manual", "Nightly"]
    assert saved_defaults == ["Nightly", "Nightly"]
    assert all(run["settings"].default_run_parameters == {"interval": {"value": 7}} for run in runs)


def test_explicit_defaults_skip_the_saved_flow(
    runs: list[dict[str, Any]],
    saved_defaults: list[str | None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _in_flow_run(monkeypatch, {"flow_name": "Nightly"})

    _session().run(QubitTargets(["0"]), STEPS, default_run_parameters={"shots": 64})

    assert saved_defaults == []
    assert runs[0]["settings"].default_run_parameters == {"shots": {"value": 64}}
    assert runs[0]["settings"].flow_name == "Nightly"


@pytest.mark.parametrize("parameters", [{}, {"flow_name": None}, {"flow_name": "  "}])
def test_a_flow_run_started_without_qdash_takes_the_prefect_flow_name(
    runs: list[dict[str, Any]],
    saved_defaults: list[str | None],
    monkeypatch: pytest.MonkeyPatch,
    parameters: dict[str, Any],
) -> None:
    _in_flow_run(monkeypatch, parameters)

    _session().run(QubitTargets(["0"]), STEPS)

    assert runs[0]["settings"].flow_name == "nightly-calibration"
    # The Prefect flow name is not a saved flow: no defaults are looked up by it.
    assert saved_defaults == [None]
    assert runs[0]["settings"].default_run_parameters == {}


def test_outside_a_flow_run_the_name_is_unset_unless_passed(
    runs: list[dict[str, Any]],
    saved_defaults: list[str | None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _outside_flow_run(monkeypatch)

    _session().run(QubitTargets(["0"]), STEPS)
    _session().run(QubitTargets(["0"]), STEPS, name="Nightly")

    assert [run["settings"].flow_name for run in runs] == [None, "Nightly"]
    # Outside QDash a passed name still selects its saved flow's defaults, as before.
    assert saved_defaults == [None, "Nightly"]
    assert runs[0]["settings"].snapshot.execution_id is None
    assert runs[1]["settings"].default_run_parameters == {"interval": {"value": 7}}


def test_first_party_templates_do_not_forward_the_run_name() -> None:
    """Every template leaves the run name to the launch and keeps the injected parameter."""
    import ast
    import inspect
    from pathlib import Path

    import qdash.workflow

    templates = sorted((Path(qdash.workflow.__file__).parent / "templates").glob("*.py"))
    checked = 0
    for path in templates:
        tree = ast.parse(path.read_text())
        runs_in_file = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
        ]
        for call in runs_in_file:
            assert "name" not in {kw.arg for kw in call.keywords}, path.name
        if not runs_in_file:
            continue
        checked += 1
        flows = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and any("calibration_flow" in ast.unparse(d) for d in node.decorator_list)
        ]
        assert flows, path.name
        for flow in flows:
            params = {a.arg for a in flow.args.args + flow.args.kwonlyargs}
            assert {"flow_name", "project_id"} <= params, (path.name, flow.name)
    assert checked >= 15
    assert "name=flow_name" not in inspect.getsource(qdash.workflow)
