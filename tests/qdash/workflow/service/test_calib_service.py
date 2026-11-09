"""The public CalibService: a small author contract over QDash-owned execution."""

from __future__ import annotations

import dataclasses
import inspect
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service.calib_service import LEGACY_OPTION_MIGRATIONS, CalibService
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets
from tests.qdash.workflow.context_helpers import grant_all_contexts, granted_context


@pytest.fixture
def recorded_runs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record what ``CalibService.run`` hands to the internal runner."""
    runs: list[dict[str, Any]] = []

    def run_calibration(settings: Any, targets: Any, steps: Any) -> dict[str, Any]:
        runs.append({"settings": settings, "targets": targets, "steps": steps})
        return {"candidate_qids": targets.to_qids(settings.chip_id)}

    monkeypatch.setattr("qdash.workflow.service._internal.runs.run_calibration", run_calibration)
    monkeypatch.setattr(
        "qdash.workflow.service._internal.runs.load_flow_default_run_parameters",
        lambda project_id, flow_name: {"interval": {"value": 1}} if flow_name else {},
    )
    return runs


def test_constructor_surface_is_context_and_run_metadata_only() -> None:
    parameters = inspect.signature(CalibService.__init__).parameters
    named = [
        name
        for name, parameter in parameters.items()
        if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    assert named == [
        "self",
        "username",
        "chip_id",
        "project_id",
        "flow_name",
        "tags",
        "note",
        "default_run_parameters",
    ]
    assert list(inspect.signature(CalibService.from_context).parameters) == [
        "context",
        "flow_name",
        "tags",
        "note",
        "default_run_parameters",
    ]
    public = {name for name in vars(CalibService) if not name.startswith("_")}
    assert public == {
        "from_context",
        "run",
        "context",
        "username",
        "chip_id",
        "project_id",
        "backend_name",
        "flow_name",
        "tags",
        "note",
        "default_run_parameters",
    }
    assert not hasattr(CalibService, "__getattr__")


@pytest.mark.parametrize("name", sorted(LEGACY_OPTION_MIGRATIONS))
def test_every_removed_option_fails_with_its_migration(name: str) -> None:
    options: dict[str, Any] = {name: object()}
    with pytest.raises(TypeError) as raised:
        CalibService("alice", "chip-1", **options)

    message = str(raised.value)
    assert f"{name}: {LEGACY_OPTION_MIGRATIONS[name]}" in message
    assert "services.md" in message


def test_removed_options_are_reported_together_before_any_lookup(monkeypatch) -> None:
    resolve = MagicMock()
    monkeypatch.setattr("qdash.workflow.service.calib_service.resolve_calib_context", resolve)

    with pytest.raises(TypeError) as raised:
        CalibService(
            "alice",
            "chip-1",
            qids=["0"],
            use_lock=False,
            snapshot_exempt_tasks={"Configure"},
        )

    message = str(raised.value)
    assert "qids: pass targets to run()" in message
    assert "use_lock:" in message
    assert "snapshot_exempt_tasks:" in message
    resolve.assert_not_called()


def test_positional_targets_name_the_removed_parameter() -> None:
    with pytest.raises(TypeError, match=r"positional argument 3 \(qids\): pass targets to run"):
        CalibService("alice", "chip-1", ["0", "1"])


def test_unknown_option_lists_the_accepted_ones() -> None:
    with pytest.raises(TypeError, match="accepts flow_name, tags, note and default_run_parameters"):
        CalibService("alice", "chip-1", colour="blue")


def test_flow_entry_resolves_and_authorizes_the_context(monkeypatch, recorded_runs) -> None:
    directory = grant_all_contexts(monkeypatch)

    cal = CalibService("alice", "chip-1", project_id="project-1", flow_name="nightly")

    assert directory.checked == [("alice", "project-1")]
    assert (cal.username, cal.chip_id, cal.project_id) == ("alice", "chip-1", "project-1")
    assert cal.context.project_id == "project-1"


def test_from_context_requires_a_resolved_context() -> None:
    with pytest.raises(TypeError, match="resolve_calib_context"):
        CalibService.from_context(object())  # type: ignore[arg-type]


def _deployment_github(monkeypatch: pytest.MonkeyPatch, github: dict[str, Any]) -> None:
    monkeypatch.setattr(
        "qdash.common.config.loader.ConfigLoader.load_workflow", lambda: {"github": github}
    )


def _context_on(backend: str) -> Any:
    # Backends listed in the deployment depend on the host; pin the one under test.
    return dataclasses.replace(granted_context(project_id="project-1"), backend_name=backend)


def test_run_hands_typed_settings_to_qdash_owned_execution(monkeypatch, recorded_runs) -> None:
    _deployment_github(monkeypatch, {"enabled": True, "branch": "calibration"})
    context = _context_on("qubex")
    cal = CalibService.from_context(
        context,
        flow_name="nightly",
        tags=["t"],
        note={"why": "test"},
        default_run_parameters={"readout_duration": 1024},
    )
    steps = [CustomOneQubit(tasks=[TaskCall(name="CheckRabi")])]

    result = cal.run(QubitTargets(["0"]), steps=steps)

    [run] = recorded_runs
    settings = run["settings"]
    assert result == {"candidate_qids": ["0"]}
    assert run["steps"] is steps
    assert (settings.username, settings.chip_id, settings.project_id) == (
        "alice",
        "chip-1",
        "project-1",
    )
    assert settings.backend_name == context.backend_name
    assert (settings.flow_name, settings.tags, settings.note) == ("nightly", ["t"], {"why": "test"})
    assert settings.default_run_parameters == {"readout_duration": {"value": 1024}}
    # Per-task defaults, snapshots and force updates are not workflow settings.
    assert settings.task_defaults == {}
    assert settings.snapshot.active is False
    assert settings.force_update_params is False
    assert settings.github.pull is True
    assert settings.github.push.enabled is True
    assert settings.github.push.branch == "calibration"


@pytest.mark.parametrize(
    ("github", "backend"),
    [
        ({"enabled": False}, "qubex"),
        ({"enabled": "true"}, "qubex"),
        ({"enabled": True}, "fake"),
    ],
)
def test_runs_follow_the_deployment_github_policy(
    monkeypatch, recorded_runs, github, backend
) -> None:
    """A disabled deployment or a backend without a config repository never syncs."""
    from qdash.workflow.service._internal.settings import GitHubPolicy

    _deployment_github(monkeypatch, github)

    CalibService.from_context(_context_on(backend)).run(QubitTargets(["0"]), [])

    assert recorded_runs[0]["settings"].github == GitHubPolicy.disabled()


def test_deployment_policy_defaults_to_enabled_on_main(monkeypatch) -> None:
    from qdash.workflow.service._internal.settings import GitHubPolicy

    _deployment_github(monkeypatch, {})

    assert GitHubPolicy.from_deployment("qubex") == GitHubPolicy.pull_and_push(branch="main")


def test_raw_session_settings_never_sync_github() -> None:
    from qdash.workflow.service._internal.settings import GitHubPolicy, SessionSettings

    settings = SessionSettings(
        username="alice", chip_id="chip-1", project_id="project-1", backend_name="qubex"
    )

    assert settings.github == GitHubPolicy.disabled()


def test_saved_flow_defaults_apply_when_the_workflow_sets_none(recorded_runs) -> None:
    CalibService.from_context(granted_context(), flow_name="nightly").run(QubitTargets(["0"]), [])
    CalibService.from_context(granted_context()).run(QubitTargets(["0"]), [])

    assert recorded_runs[0]["settings"].default_run_parameters == {"interval": {"value": 1}}
    assert recorded_runs[1]["settings"].default_run_parameters == {}


def test_a_flow_with_source_execution_id_reruns_from_its_snapshot(
    monkeypatch, recorded_runs
) -> None:
    monkeypatch.setattr(
        "qdash.workflow.service._internal.runs.read_source_execution_id_from_context",
        lambda: "exec-source",
    )

    CalibService.from_context(granted_context()).run(QubitTargets(["0"]), [])

    snapshot = recorded_runs[0]["settings"].snapshot
    assert (snapshot.execution_id, snapshot.task_id, snapshot.exempt_tasks) == (
        "exec-source",
        None,
        frozenset(),
    )


def test_run_metadata_is_copied_and_the_service_runs_again(recorded_runs) -> None:
    note = {"nested": {"value": 1}}
    tags = ["a"]
    cal = CalibService.from_context(granted_context(), tags=tags, note=note)
    note["nested"]["value"] = 2
    tags.append("b")

    cal.run(QubitTargets(["0"]), [])
    cal.run(QubitTargets(["1"]), [])

    assert [run["settings"].note for run in recorded_runs] == [{"nested": {"value": 1}}] * 2
    assert [run["settings"].tags for run in recorded_runs] == [["a"]] * 2
    assert cal.note == {"nested": {"value": 1}}


def test_internal_runs_keep_an_explicit_operational_policy(monkeypatch) -> None:
    """``run_calibration`` runs the settings it is given; it does not reapply defaults."""
    from qdash.workflow.service._internal import runs
    from qdash.workflow.service._internal.settings import GitHubPolicy

    _deployment_github(monkeypatch, {"enabled": True})
    monkeypatch.setattr("qdash.workflow.service.flow_targets.read_target_override", lambda: None)
    sessions: list[Any] = []

    class RecordingSession:
        def __init__(self, settings: Any, repositories: Any = None) -> None:
            self.settings = settings
            sessions.append(self)

        def run_pipeline(self, targets: Any, steps: Any) -> dict[str, Any]:
            return {}

    monkeypatch.setattr(runs, "CalibSession", RecordingSession)
    settings = runs.workflow_settings(
        _context_on("qubex"),
        flow_name="maintenance",
        tags=None,
        note=None,
        default_run_parameters={"interval": 1},
    ).model_copy(update={"github": GitHubPolicy.disabled(), "configuration_mode": "ge-ef-cr"})

    runs.run_calibration(settings, QubitTargets(["0"]), [])

    [session] = sessions
    assert session.settings.github == GitHubPolicy.disabled()
    assert session.settings.configuration_mode == "ge-ef-cr"
