"""Workflow services calibrate standalone qubits and refuse MUX work on them."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

import pytest

from qdash.common.mux_mapping import MuxMapping, MuxMappingError
from qdash.datamodel.task_call import StepCalls, TaskCall
from qdash.workflow.service._internal.scheduling_tasks import _should_skip_task_for_qid
from qdash.workflow.service.targets import (
    AllMuxTargets,
    AllQubitTargets,
    MuxTargets,
    QubitTargets,
)

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession

GROUPS = {9: ["0", "17", "5", "2"], 4: ["12", "3"]}
KNOWN = ["0", "1", "2", "3", "5", "6", "12", "17", "20"]


def _mapping() -> MuxMapping:
    return MuxMapping.from_groups(GROUPS, known_qids=KNOWN)


def _no_mux_mapping() -> MuxMapping:
    return MuxMapping.from_groups({}, known_qids=["0", "1", "2"])


# ---------------------------------------------------------------- MUX tasks


def test_mux_task_on_a_standalone_qubit_is_rejected_not_skipped() -> None:
    session = cast("CalibSession", SimpleNamespace(mux_mapping=_mapping()))

    with patch("qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=True):
        with pytest.raises(MuxMappingError, match="cannot run on standalone qubit 6"):
            _should_skip_task_for_qid("CheckResonatorSpectroscopy", "6", "fake", session)
        assert not _should_skip_task_for_qid("CheckResonatorSpectroscopy", "0", "fake", session)
    with patch("qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=False):
        assert not _should_skip_task_for_qid("CheckRabi", "6", "fake", session)


def _plan() -> StepCalls:
    return StepCalls(step_id="check", calls=(TaskCall(name="CheckRabi"),))


def _session(mapping: MuxMapping, backend_name: str = "fake") -> CalibSession:
    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service._internal.settings import GitHubPolicy, SessionSettings

    session = CalibSession(
        SessionSettings(
            username="alice",
            chip_id="chip-x",
            project_id="project-1",
            backend_name=backend_name,
            github=GitHubPolicy.disabled(),
        )
    )
    session._mux_mapping = mapping
    return session


def test_calib_session_refuses_mux_tasks_on_standalone_before_running() -> None:
    session = _session(_mapping())

    with patch("qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=True):
        with pytest.raises(MuxMappingError, match=r"standalone qubits \['6', '20'\]"):
            session._reject_mux_task_on_standalone("CheckResonatorSpectroscopy", ["0", "6", "20"])
        session._reject_mux_task_on_standalone("CheckResonatorSpectroscopy", ["0", "12"])
    with patch("qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=False):
        session._reject_mux_task_on_standalone("CheckRabi", ["6"])


def test_worker_spec_rejects_owner_mapping_failure_before_worker_creation() -> None:
    session = _session(_mapping())
    session._mux_mapping = None
    session.execution_id = "owner-execution"
    with (
        patch(
            "qdash.workflow.service._internal.session.resolve_chip_mux_mapping",
            side_effect=[MuxMappingError("Topology unavailable"), _no_mux_mapping()],
        ) as resolve_mapping,
        patch("qdash.workflow.service._internal.session.WorkerSpec") as worker_spec,
    ):
        with pytest.raises(MuxMappingError, match="Topology unavailable"):
            session.worker_spec()
        # Even if the next lookup would succeed with changed membership, no
        # unresolved spec may escape for a worker to perform that lookup.
        resolve_mapping.assert_called_once()
        worker_spec.assert_not_called()


def test_owner_mapping_failure_is_final_for_late_worker_specs() -> None:
    """A failure seen earlier (e.g. a whole-chip scope) is not retried by worker_spec."""
    session = _session(_mapping())
    session._mux_mapping = None
    session.execution_id = "owner-execution"
    with (
        patch(
            "qdash.workflow.service._internal.session.resolve_chip_mux_mapping",
            side_effect=[MuxMappingError("Topology unavailable"), _mapping()],
        ) as resolve_mapping,
        patch("qdash.workflow.service._internal.session.WorkerSpec") as worker_spec,
    ):
        # A non-qubex owner tolerates the failure by reserving the whole chip.
        assert session.resource_scope({"qid": "0"}).exclusive
        # The topology is repaired afterwards, but the owner never planned with it.
        with pytest.raises(MuxMappingError, match="Topology unavailable"):
            session.worker_spec()
        with pytest.raises(MuxMappingError, match="Topology unavailable"):
            _ = session.mux_mapping
        resolve_mapping.assert_called_once()
        worker_spec.assert_not_called()


def test_worker_spec_pins_the_owner_mapping() -> None:
    from qdash.common.mux_mapping import MuxMappingSnapshot

    session = _session(_mapping())
    session.execution_id = "owner-execution"
    with patch(
        "qdash.workflow.service._internal.session.resolve_chip_mux_mapping",
        side_effect=AssertionError("the owner's mapping is already resolved"),
    ):
        spec = session.worker_spec()

    assert spec.mux_mapping == MuxMappingSnapshot.of(_mapping())
    assert spec.mux_mapping.to_mapping().groups == _mapping().groups


def test_workers_never_resolve_a_mapping_of_their_own() -> None:
    """A worker without its owner's mapping is refused before any backend exists."""
    from pydantic import ValidationError

    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service._internal.settings import (
        GitHubPolicy,
        SessionSettings,
        WorkerLease,
        WorkerSpec,
    )

    settings = SessionSettings(
        username="alice",
        chip_id="chip-x",
        project_id="project-1",
        backend_name="fake",
        github=GitHubPolicy.disabled(),
    ).for_worker()
    lease = WorkerLease(execution_id="owner-execution")

    with pytest.raises(ValidationError, match="mux_mapping"):
        WorkerSpec(settings=settings, lease=lease)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="MUX mapping its owner resolved"):
        CalibSession(settings, lease=lease)


def _reserved_session(mapping: MuxMapping) -> tuple[CalibSession, MagicMock]:
    """A session holding a whole-chip reservation, with a mocked orchestrator."""
    from qdash.common.execution_resources import ExecutionResourceScope

    session = _session(mapping, backend_name="qubex")
    session._lock_acquired = True
    session._reserved_scope = ExecutionResourceScope("chip-x", exclusive=True)
    orchestrator = MagicMock()
    orchestrator.run_task.return_value = {"task_id": "t-1"}
    orchestrator.run_task_batch.return_value = {}
    session._orchestrator = orchestrator
    return session, orchestrator


def test_whole_chip_reservation_refuses_unknown_qubits_before_dispatch() -> None:
    session, orchestrator = _reserved_session(_mapping())

    with pytest.raises(MuxMappingError, match=r"targets \['999'\] are not defined"):
        session.execute_task("CheckRabi", "999")
    with pytest.raises(MuxMappingError, match=r"targets \['999'\] are not defined"):
        session.execute_task_batch("CheckRabi", ["0", "999", "6"])
    with pytest.raises(MuxMappingError, match=r"targets \['0-999'\] are not defined"):
        session.execute_task("CheckCrossResonance", "0-999")
    with pytest.raises(MuxMappingError, match=r"targets \['999-0'\] are not defined"):
        session.execute_task_batch("CheckCrossResonance", ["0-17", "999-0"])
    with pytest.raises(MuxMappingError, match="not defined"):
        session.execute_task("CheckRabi", "")

    orchestrator.run_task.assert_not_called()
    orchestrator.run_task_batch.assert_not_called()


def test_whole_chip_reservation_still_runs_known_and_system_targets() -> None:
    session, orchestrator = _reserved_session(_mapping())

    with patch("qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=False):
        session.execute_task("CheckRabi", "Q06")  # standalone, normalized qid format
        session.execute_task("CheckRabi", "17")  # MUX member
        session.execute_task("CheckCrossResonance", "0-17")
        session.execute_task_batch("CheckRabi", ["0", "6", "20"])
        session.execute_task_batch("CheckCrossResonance", ["0-17", "12-3"])
    with patch("qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=True):
        session.execute_task("CheckResonatorSpectroscopy", "12")
    # System and global tasks address no qubit and keep their placeholder target.
    session.execute_task("ConfigureAll", "", parameters={"run": {"mux_ids": [9]}})
    session.execute_task("CheckStatus", "")

    assert orchestrator.run_task.call_count == 6
    assert orchestrator.run_task_batch.call_count == 2


@pytest.mark.parametrize("mux_ids", [[7], [9, 7], [-1], "9"])
def test_configure_all_rejects_mux_ids_outside_the_topology_before_dispatch(
    mux_ids: Any,
) -> None:
    """A whole-chip reservation alone must not let an undefined MUX reach the boxes."""
    session, orchestrator = _reserved_session(_mapping())

    with pytest.raises(MuxMappingError):
        session.execute_task("ConfigureAll", "", parameters={"run": {"mux_ids": mux_ids}})

    orchestrator.run_task.assert_not_called()


def test_configure_all_keeps_its_default_selection() -> None:
    """Without mux_ids (or with []), ConfigureAll keeps its own default and a chip lock."""
    session, orchestrator = _reserved_session(_mapping())

    session.execute_task("ConfigureAll", "")
    session.execute_task("ConfigureAll", "", parameters={"run": {"mux_ids": []}})

    assert orchestrator.run_task.call_count == 2


def test_legacy_unbounded_chip_skips_membership_checks() -> None:
    session, orchestrator = _reserved_session(MuxMapping.legacy())

    with patch("qdash.workflow.calibtasks.active_protocols.is_mux_task", return_value=False):
        session.execute_task("CheckRabi", "999")
        session.execute_task_batch("CheckCrossResonance", ["998-999"])

    orchestrator.run_task.assert_called_once()
    orchestrator.run_task_batch.assert_called_once()


# ------------------------------------------------------------------ targets


def test_all_qubit_targets_include_mux_members_and_standalone_qubits() -> None:
    captured: list[list[int]] = []

    def to_qids(self: MuxTargets, chip_id: str, *, mux_mapping: Any = None) -> list[str]:
        captured.append(list(self.mux_ids))
        mapping = cast("MuxMapping", mux_mapping)
        return mapping.qids_for_muxes(self.mux_ids, self.exclude_qids)

    with patch.object(MuxTargets, "to_qids", to_qids):
        qids = AllQubitTargets(exclude_qids=["5", "20"]).to_qids("chip-x", mux_mapping=_mapping())

    assert captured == [[4, 9]]
    assert qids == ["0", "1", "2", "3", "6", "12", "17"]


def test_all_qubit_targets_may_exclude_every_mux_member() -> None:
    """Exclusions that empty every MUX still select the standalone qubits."""
    members = [qid for qids in GROUPS.values() for qid in qids]
    with patch.object(MuxTargets, "to_qids", side_effect=AssertionError("no MUX member left")):
        qids = AllQubitTargets(exclude_qids=members).to_qids("chip-x", mux_mapping=_mapping())

    assert qids == ["1", "6", "20"]


def test_all_qubit_targets_skip_muxes_emptied_by_prefixed_exclusions() -> None:
    captured: list[list[int]] = []

    def to_qids(self: MuxTargets, chip_id: str, *, mux_mapping: Any = None) -> list[str]:
        captured.append(list(self.mux_ids))
        return cast("MuxMapping", mux_mapping).qids_for_muxes(self.mux_ids, self.exclude_qids)

    with patch.object(MuxTargets, "to_qids", to_qids):
        qids = AllQubitTargets(exclude_qids=["Q12", "Q03", "Q06"]).to_qids(
            "chip-x", mux_mapping=_mapping()
        )

    assert captured == [[9]]
    assert qids == ["0", "1", "2", "5", "17", "20"]


def test_all_mux_targets_reject_a_declared_mux_without_wiring(tmp_path) -> None:
    """Every declared MUX must be wired; AllMuxTargets never returns part of the chip."""
    import yaml

    wiring = tmp_path / "wiring.yaml"
    # Only MUX 9 is wired; the topology also declares MUX 4.
    wiring.write_text(
        yaml.safe_dump(
            {"chip-x": [{"mux": 9, "ctrl": ["A-0", "A-1", "A-2", "A-3"], "read_out": "RA"}]}
        )
    )
    paths = MagicMock()
    paths.wiring_yaml.return_value = wiring
    with patch("qdash.workflow.service.targets.get_qubex_paths", return_value=paths):
        with pytest.raises(MuxMappingError, match=r"MUXes \[4\].*no row in the wiring"):
            AllMuxTargets().to_qids("chip-x", mux_mapping=_mapping())
        with pytest.raises(MuxMappingError, match=r"MUXes \[4\]"):
            AllQubitTargets().to_qids("chip-x", mux_mapping=_mapping())
        # Excluding MUX 4 entirely needs no wiring for it.
        assert AllQubitTargets(exclude_qids=["12", "3"]).to_qids(
            "chip-x", mux_mapping=_mapping()
        ) == ["0", "1", "2", "5", "6", "17", "20"]


def test_all_qubit_targets_on_a_chip_without_mux_skip_wiring() -> None:
    with patch.object(MuxTargets, "to_qids", side_effect=AssertionError("no MUX to resolve")):
        assert AllQubitTargets().to_qids("chip-x", mux_mapping=_no_mux_mapping()) == [
            "0",
            "1",
            "2",
        ]
        with pytest.raises(ValueError, match="excluded"):
            AllQubitTargets(exclude_qids=["0", "1", "2"]).to_qids(
                "chip-x", mux_mapping=_no_mux_mapping()
            )


def test_all_qubit_targets_without_topology_match_all_mux_targets() -> None:
    captured: list[list[int]] = []

    def to_qids(self: MuxTargets, chip_id: str, *, mux_mapping: Any = None) -> list[str]:
        captured.append(list(self.mux_ids))
        return []

    with patch.object(MuxTargets, "to_qids", to_qids):
        AllQubitTargets().to_qids("chip-x", mux_mapping=MuxMapping.legacy())

    assert captured == [list(range(16))]


def test_all_mux_targets_select_only_declared_muxes() -> None:
    captured: list[list[int]] = []

    def to_qids(self: MuxTargets, chip_id: str, *, mux_mapping: Any = None) -> list[str]:
        captured.append(list(self.mux_ids))
        return []

    with patch.object(MuxTargets, "to_qids", to_qids):
        AllMuxTargets().to_qids("chip-x", mux_mapping=_mapping())
        with pytest.raises(ValueError, match="declares no MUX"):
            AllMuxTargets().to_qids("chip-x", mux_mapping=_no_mux_mapping())

    assert captured == [[4, 9]]


# -------------------------------------------------------------------- steps


def test_qubit_targets_pass_standalone_qubits_to_the_strategy() -> None:
    from qdash.workflow.service.steps.one_qubit import _execute_scheduled_one_qubit

    session = SimpleNamespace(mux_mapping=_mapping())
    strategy = MagicMock()
    strategy.execute.return_value = {}

    with patch("qdash.workflow.service.strategy.get_one_qubit_strategy", return_value=strategy):
        _execute_scheduled_one_qubit(
            session,  # type: ignore[arg-type]
            qids=["20", "17", "6", "12"],
            plan=_plan(),
            stage_name="check",
            execution_mode="parallel_by_mux",
        )

    config = strategy.execute.call_args.args[1]
    assert config.mux_ids == [4, 9]
    assert config.standalone_qids == ["6", "20"]
    assert config.qids == ["20", "17", "6", "12"]


def test_scheduled_strategy_runs_the_standalone_stage(tmp_path) -> None:
    import yaml

    from qdash.workflow.service.strategy import OneQubitConfig, OneQubitParallelByMuxStrategy

    wiring = tmp_path / "wiring.yaml"
    wiring.write_text(
        yaml.safe_dump(
            {
                "chip-x": [
                    {"mux": 9, "ctrl": ["A-0", "A-1", "A-2", "A-3"], "read_out": "RA"},
                    {"mux": 4, "ctrl": ["B-0", "B-1"], "read_out": "RB"},
                ]
            }
        )
    )
    session = MagicMock(chip_id="chip-x", mux_mapping=_mapping(), backend_name="fake")
    calls: list[list[list[str]]] = []

    def run(mux_groups: list[list[str]], **_kwargs: Any) -> dict[str, Any]:
        calls.append(mux_groups)
        return {qid: {"status": "success"} for group in mux_groups for qid in group}

    config = OneQubitConfig(
        mux_ids=[4],
        exclude_qids=[],
        plan=_plan(),
        standalone_qids=["20", "6"],
    )
    strategy = OneQubitParallelByMuxStrategy()
    with (
        patch.object(strategy, "_get_wiring_config_path", return_value=str(wiring)),
        patch("qdash.workflow.service.strategy.run_mux_calibrations_parallel", run),
    ):
        results = strategy.execute(session, config)

    # MUX stage first, then one sequential group with every standalone qubit.
    assert calls == [[["12", "3"]], [["6", "20"]]]
    assert set(results["Box_STANDALONE"]) == {"6", "20"}


def test_configure_all_refuses_to_derive_muxes_from_standalone_qubits() -> None:
    from qdash.workflow.service.steps.box_setup import ConfigureAll

    service = SimpleNamespace(chip_id="chip-x", mux_mapping=_mapping())

    with pytest.raises(ValueError, match=r"standalone qubits \['6'\]"):
        ConfigureAll()._resolve_mux_ids(service, QubitTargets(["17", "6"]))  # type: ignore[arg-type]
    assert ConfigureAll(mux_ids=[9])._resolve_mux_ids(service, QubitTargets(["6"])) == [9]  # type: ignore[arg-type]


def test_bring_up_refuses_standalone_qubit_targets() -> None:
    from qdash.workflow.service.steps import StepContext
    from qdash.workflow.service.steps.bringup import BringUp

    service = MagicMock(chip_id="chip-x", mux_mapping=_mapping())

    with (
        patch("qdash.workflow.service.steps.bringup.get_run_logger"),
        pytest.raises(ValueError, match="cannot target standalone qubits"),
    ):
        BringUp().execute(service, QubitTargets(["0", "20"]), StepContext())


def test_pipeline_plan_reserves_the_chip_for_standalone_targets() -> None:
    from qdash.workflow.service.pipeline_resources import plan_pipeline_resources

    planned = plan_pipeline_resources(
        "chip-x", QubitTargets(["6"]), [], mux_mapping=_no_mux_mapping()
    )

    assert planned.exclusive


def test_mux_task_on_a_standalone_qubit_fails_only_that_call() -> None:
    from qdash.workflow.service._internal.scheduling_tasks import (
        _execute_single_qubit_with_session,
    )

    session = MagicMock(backend_name="fake", mux_mapping=_mapping())
    session.execute_task.return_value = {"task_id": "t-1"}
    plan = StepCalls(
        step_id="bringup",
        calls=(TaskCall(name="CheckResonatorSpectroscopy"), TaskCall(name="CheckRabi")),
        continue_on_failure=True,
    )

    with patch(
        "qdash.workflow.calibtasks.active_protocols.is_mux_task",
        side_effect=lambda name, _backend: name == "CheckResonatorSpectroscopy",
    ):
        result = _execute_single_qubit_with_session(session, "6", plan, MagicMock())

    # The MUX call fails without touching hardware; the qubit-level call still runs.
    assert result["status"] == "failed"
    statuses = [call["status"] for call in result["calls"]]
    assert statuses == ["failed", "success"]
    assert "standalone qubit 6" in result["calls"][0]["error"]
    session.execute_task.assert_called_once()
    assert session.execute_task.call_args.args[:2] == ("CheckRabi", "6")
