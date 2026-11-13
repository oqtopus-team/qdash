"""The Qubex backend refuses MUX layouts it would drive differently.

Qubex places qubit index ``i`` in MUX ``i // 4`` on control slot ``i % 4`` and
does not read QDash topologies. Every path that builds or connects a Qubex
``Experiment`` must reject a topology whose ``muxes`` disagree, or that has
standalone (non-multiplexed) qubits, before any hardware access. Other
backends keep arbitrary layouts.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from qdash.common.config.loader import ConfigLoader
from qdash.common.config.topology import load_topology
from qdash.common.mux_mapping import (
    MuxMapping,
    MuxMappingError,
    check_qubex_mux_mapping,
    qubex_mux_mapping_errors,
)
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.backend.qubex import QubexBackend

# Same qubits as the legacy layout, but MUX 0 and MUX 1 swap members.
SWAPPED_MEMBERSHIP = {0: [4, 5, 6, 7], 1: [0, 1, 2, 3]}
# Legacy membership, but slots 0 and 1 of MUX 0 are swapped.
SWAPPED_SLOTS = {0: [1, 0, 2, 3], 1: [4, 5, 6, 7]}
COMPATIBLE = {0: [0, 1, 2, 3], 1: [4, 5, 6, 7]}


@pytest.fixture
def bundled_topologies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", ConfigLoader.LOCAL_CONFIG_DIR)
    load_topology.cache_clear()
    yield
    load_topology.cache_clear()


@pytest.fixture
def experiment(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stand-in for ``qubex.Experiment``; any call means hardware was touched."""
    factory = MagicMock()
    monkeypatch.setattr("qubex.Experiment", factory)
    return factory


def _config(**extra: Any) -> dict[str, Any]:
    return {
        "task_type": "qubit",
        "qids": ["0"],
        "chip_id": "chip-1",
        "classifier_dir": "classifiers",
        **extra,
    }


# ---------------------------------------------------------------- the rule


@pytest.mark.parametrize(
    ("groups", "fragment"),
    [
        (SWAPPED_MEMBERSHIP, "MUX 0 lists qubits [4, 5, 6, 7] but Qubex drives [0, 1, 2, 3]"),
        (SWAPPED_SLOTS, "MUX 0 lists qubits [1, 0, 2, 3] but Qubex drives [0, 1, 2, 3]"),
        ({0: [0, 2]}, "MUX 0 lists qubits [0, 2] but Qubex drives [0, 1]"),
        ({3: [12, 13, 14, 15, 16]}, "MUX 3 lists qubits [12, 13, 14, 15, 16]"),
    ],
)
def test_incompatible_groups_are_rejected_with_the_expected_layout(
    groups: dict[int, list[int]], fragment: str
) -> None:
    mapping = MuxMapping.from_groups(groups, topology_id="custom")

    with pytest.raises(MuxMappingError) as error:
        check_qubex_mux_mapping(mapping)

    message = str(error.value)
    assert fragment in message
    assert "topology custom" in message
    assert "4N, 4N+1, 4N+2, 4N+3" in message


def test_legacy_and_compatible_layouts_pass() -> None:
    assert qubex_mux_mapping_errors(MuxMapping.legacy()) == []
    assert qubex_mux_mapping_errors(MuxMapping.from_groups(COMPATIBLE)) == []
    # Trailing qubits of a MUX may be left out; sparse MUX IDs are fine.
    assert qubex_mux_mapping_errors(MuxMapping.from_groups({5: [20, 21], 9: [36]})) == []


def test_standalone_qubits_are_rejected_not_treated_as_qid_div_4() -> None:
    # Qubit 3 is known but in no MUX; Qubex would silently put it in MUX 0.
    partial = MuxMapping.from_groups(
        {0: [0, 1, 2]}, known_qids=["0", "1", "2", "3"], topology_id="p"
    )
    no_mux = MuxMapping.from_groups({}, known_qids=["0", "1"], topology_id="none")

    with pytest.raises(MuxMappingError, match=r"qubits \[3\] are standalone"):
        check_qubex_mux_mapping(partial)
    with pytest.raises(MuxMappingError, match=r"qubits \[0, 1\] are standalone"):
        check_qubex_mux_mapping(no_mux)


def test_legacy_templates_follow_their_normalized_layout() -> None:
    from qdash.common.config.topology import TopologyDefinition

    base: dict[str, Any] = {
        "id": "old",
        "name": "Old",
        "grid_size": 2,
        "num_qubits": 4,
        "qubits": {q: {"row": q // 2, "col": q % 2} for q in range(4)},
        "couplings": [],
    }
    # Raw template dicts: the legacy ``mux`` key is normalized by the model validator.
    derived = TopologyDefinition.model_validate({**base, "mux": {"enabled": True, "size": 2}})
    disabled = TopologyDefinition.model_validate({**base, "mux": {"enabled": False}})

    # mux.enabled without groups is Qubex's own layout by construction.
    assert qubex_mux_mapping_errors(MuxMapping.from_topology(derived)) == []
    # mux.enabled: false now means no MUX, which Qubex cannot drive.
    assert qubex_mux_mapping_errors(MuxMapping.from_topology(disabled)) != []


def test_backend_rejects_standalone_qubits_before_building_the_experiment(
    experiment: MagicMock,
) -> None:
    mapping = MuxMapping.from_groups({0: [0, 1]}, known_qids=["0", "1", "2"])

    with pytest.raises(MuxMappingError, match="standalone"):
        QubexBackend(_config(), mux_mapping=mapping)
    experiment.assert_not_called()


@pytest.mark.parametrize(
    ("topology_id", "num_muxes"), [("square-lattice-mux-16", 4), ("square-lattice-mux-64", 16)]
)
def test_bundled_mux_templates_are_qubex_compatible(
    topology_id: str, num_muxes: int, bundled_topologies
) -> None:
    mapping = MuxMapping.from_topology(load_topology(topology_id))

    assert mapping.is_explicit
    assert mapping.mux_ids == list(range(num_muxes))
    assert qubex_mux_mapping_errors(mapping) == []


# ---------------------------------------------------------- QubexBackend


@pytest.mark.parametrize("groups", [SWAPPED_MEMBERSHIP, SWAPPED_SLOTS])
def test_backend_rejects_an_incompatible_mapping_at_construction(
    groups: dict[int, list[int]], experiment: MagicMock
) -> None:
    with pytest.raises(MuxMappingError, match="not supported by the Qubex backend"):
        QubexBackend(_config(), mux_mapping=MuxMapping.from_groups(groups))
    with pytest.raises(MuxMappingError):
        create_backend("qubex", _config(), mux_mapping=MuxMapping.from_groups(groups))

    experiment.assert_not_called()


def test_backend_resolves_the_chip_mapping_before_building_the_experiment(
    experiment: MagicMock,
) -> None:
    backend = QubexBackend(_config(project_id="project-1"))

    with (
        patch(
            "qdash.workflow.engine.backend.qubex.resolve_chip_mux_mapping",
            return_value=MuxMapping.from_groups(SWAPPED_SLOTS, topology_id="custom"),
        ) as resolve,
        pytest.raises(MuxMappingError, match="topology custom"),
    ):
        backend.connect()

    resolve.assert_called_once_with("project-1", "chip-1")
    experiment.assert_not_called()
    assert not backend.is_connected


def test_backend_resolves_an_explicit_topology_id(experiment: MagicMock) -> None:
    backend = QubexBackend(_config(project_id="project-1", topology_id="custom"))

    with (
        patch(
            "qdash.workflow.engine.backend.qubex.resolve_topology_mux_mapping",
            return_value=MuxMapping.from_groups(SWAPPED_MEMBERSHIP, topology_id="custom"),
        ) as resolve,
        patch("qdash.workflow.engine.backend.qubex.resolve_chip_mux_mapping") as chip_lookup,
        pytest.raises(MuxMappingError),
    ):
        backend.get_instance()

    resolve.assert_called_once_with("custom")
    chip_lookup.assert_not_called()
    experiment.assert_not_called()


@pytest.mark.parametrize("topology_id", [None, ""])
def test_backend_treats_an_empty_topology_id_as_absent(
    experiment: MagicMock, topology_id: str | None
) -> None:
    """``topology_id: None`` must not select the legacy layout over the chip's own."""
    backend = QubexBackend(_config(project_id="project-1", topology_id=topology_id))

    with (
        patch(
            "qdash.workflow.engine.backend.qubex.resolve_chip_mux_mapping",
            return_value=MuxMapping.from_groups(SWAPPED_MEMBERSHIP, topology_id="custom"),
        ) as chip_lookup,
        pytest.raises(MuxMappingError, match="topology custom"),
    ):
        backend.connect()

    chip_lookup.assert_called_once_with("project-1", "chip-1")
    experiment.assert_not_called()


def test_unusable_configured_topology_blocks_the_connection(
    experiment: MagicMock, bundled_topologies
) -> None:
    backend = QubexBackend(_config(topology_id="deleted-template"))

    with pytest.raises(MuxMappingError, match="not found"):
        backend.connect()

    experiment.assert_not_called()


def test_backend_connects_with_the_bundled_64q_template(
    experiment: MagicMock, bundled_topologies
) -> None:
    backend = QubexBackend(_config(topology_id="square-lattice-mux-64"))

    backend.connect()

    experiment.assert_called_once()
    experiment.return_value.connect.assert_called_once_with()


def test_backend_connects_with_a_compatible_mapping(experiment: MagicMock) -> None:
    backend = QubexBackend(_config(), mux_mapping=MuxMapping.from_groups(COMPATIBLE))

    backend.connect()

    experiment.assert_called_once()
    experiment.return_value.connect.assert_called_once_with()


def test_backend_without_context_keeps_the_legacy_layout(experiment: MagicMock) -> None:
    backend = QubexBackend(_config())

    backend.connect()

    assert backend.ensure_mux_mapping_compatible().source == "legacy"
    experiment.assert_called_once()


def test_fake_backend_keeps_arbitrary_groups() -> None:
    backend = create_backend(
        "fake", _config(), mux_mapping=MuxMapping.from_groups(SWAPPED_MEMBERSHIP)
    )

    assert isinstance(backend, FakeBackend)


# ------------------------------------------------------------ ConfigureAll


def test_configure_all_checks_the_layout_before_building_its_experiment(
    experiment: MagicMock,
) -> None:
    from qdash.workflow.calibtasks.qubex.box_setup.configure_all import ConfigureAll

    task = ConfigureAll()
    task.run_parameters["mux_ids"].value = [0]
    backend = QubexBackend({"chip_id": "chip-1", "topology_id": "custom"})

    with (
        patch(
            "qdash.workflow.engine.backend.qubex.resolve_topology_mux_mapping",
            return_value=MuxMapping.from_groups(SWAPPED_SLOTS),
        ),
        pytest.raises(MuxMappingError),
    ):
        task.run(backend, "")

    experiment.assert_not_called()


@pytest.mark.parametrize("mux_ids", [[99], [0, 99], [-1], [True]])
def test_configure_all_rejects_mux_ids_outside_the_topology(
    experiment: MagicMock, mux_ids: list[Any]
) -> None:
    """A direct call never hands Qubex a MUX that the chip topology does not define."""
    from qdash.workflow.calibtasks.qubex.box_setup.configure_all import ConfigureAll

    task = ConfigureAll()
    task.run_parameters["mux_ids"].value = mux_ids
    backend = QubexBackend({"chip_id": "chip-1"}, mux_mapping=MuxMapping.from_groups(COMPATIBLE))

    with pytest.raises(MuxMappingError, match="not defined"):
        task.run(backend, "")

    experiment.assert_not_called()


def test_configure_all_passes_defined_mux_ids_to_qubex(
    experiment: MagicMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from qdash.workflow.calibtasks.qubex.box_setup.configure_all import ConfigureAll

    task = ConfigureAll()
    task.run_parameters["mux_ids"].value = [1, 0]
    backend = QubexBackend(
        {"chip_id": "chip-1", "config_dir": str(tmp_path), "params_dir": str(tmp_path)},
        mux_mapping=MuxMapping.from_groups(COMPATIBLE),
    )

    task.run(backend, "")

    assert experiment.call_args.kwargs["muxes"] == [1, 0]


# ------------------------------------------------------------ orchestrator


def _calib_config(backend_name: str, mapping: MuxMapping | None) -> Any:
    from qdash.workflow.engine.config import CalibConfig

    return CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["0"],
        execution_id="exec-1",
        project_id="project-1",
        backend_name=backend_name,
        mux_mapping=mapping,
    )


def test_orchestrator_passes_the_session_mapping_to_the_backend(experiment: MagicMock) -> None:
    from types import SimpleNamespace

    from qdash.workflow.engine.orchestrator import CalibOrchestrator

    orchestrator = CalibOrchestrator(
        _calib_config("qubex", MuxMapping.from_groups(SWAPPED_MEMBERSHIP))
    )
    orchestrator._task_context = SimpleNamespace(id="manager-1")  # type: ignore[assignment]

    with (
        patch.object(QubexBackend, "save_note") as save_note,
        pytest.raises(MuxMappingError),
    ):
        orchestrator._create_backend()

    save_note.assert_not_called()
    experiment.assert_not_called()


def test_orchestrator_checks_a_resolved_mapping_before_saving_notes(
    experiment: MagicMock,
) -> None:
    from types import SimpleNamespace

    from qdash.workflow.engine.orchestrator import CalibOrchestrator

    orchestrator = CalibOrchestrator(_calib_config("qubex", None))
    orchestrator._task_context = SimpleNamespace(id="manager-1")  # type: ignore[assignment]

    with (
        patch(
            "qdash.workflow.engine.backend.qubex.resolve_chip_mux_mapping",
            return_value=MuxMapping.from_groups(SWAPPED_SLOTS),
        ),
        patch.object(QubexBackend, "save_note") as save_note,
        pytest.raises(MuxMappingError),
    ):
        orchestrator._create_backend()

    save_note.assert_not_called()
    experiment.assert_not_called()


# ------------------------------------------------------------- CalibSession

SESSION = "qdash.workflow.service._internal.session"


def _calib_session(
    monkeypatch: pytest.MonkeyPatch,
    backend_name: str,
    mapping: MuxMapping,
    lock_repo: MagicMock | None = None,
) -> tuple[Any, MagicMock]:
    """An owner session whose chip topology resolves to ``mapping``."""
    from qdash.workflow.service._internal.session import CalibSession, SessionRepositories
    from qdash.workflow.service._internal.settings import GitHubPolicy, SessionSettings

    orchestrator = MagicMock()
    if lock_repo is None:
        lock_repo = MagicMock()
        lock_repo.try_lock.return_value = True
    monkeypatch.setattr(f"{SESSION}.CalibOrchestrator", orchestrator)
    monkeypatch.setattr(f"{SESSION}.GitHubIntegration", MagicMock())
    monkeypatch.setattr(f"{SESSION}.resolve_chip_mux_mapping", lambda project_id, chip_id: mapping)
    session = CalibSession(
        SessionSettings(
            username="alice",
            chip_id="chip-1",
            project_id="project-1",
            backend_name=backend_name,
            github=GitHubPolicy.disabled(),
        ),
        repositories=SessionRepositories(lock_repo=lock_repo),
    )
    session.execution_id = "20240101-001"
    return session, orchestrator


def test_calib_session_rejects_qubex_before_locking_or_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_repo = MagicMock()
    session, orchestrator = _calib_session(
        monkeypatch, "qubex", MuxMapping.from_groups(SWAPPED_SLOTS), lock_repo
    )

    with pytest.raises(MuxMappingError, match="not supported by the Qubex backend"):
        session._initialize(["0"])

    lock_repo.try_lock.assert_not_called()
    orchestrator.assert_not_called()


def test_calib_session_pipeline_rejects_qubex_before_reserving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.workflow.service.targets import QubitTargets

    lock_repo = MagicMock()
    session, orchestrator = _calib_session(
        monkeypatch, "qubex", MuxMapping.from_groups(SWAPPED_MEMBERSHIP), lock_repo
    )
    monkeypatch.setattr(f"{SESSION}.get_run_logger", MagicMock())

    with pytest.raises(MuxMappingError, match="not supported by the Qubex backend"):
        session.run_pipeline(QubitTargets(["0"]), [])

    lock_repo.try_lock.assert_not_called()
    orchestrator.assert_not_called()


def test_calib_session_keeps_arbitrary_groups_on_the_fake_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, orchestrator = _calib_session(
        monkeypatch, "fake", MuxMapping.from_groups(SWAPPED_MEMBERSHIP)
    )

    session._initialize(["0"])

    orchestrator.assert_called_once()
    # The Execution carries the session's mapping for MUX result fan-out; only the
    # Qubex backend checks it against its own layout.
    assert orchestrator.call_args.kwargs["config"].mux_mapping is session.mux_mapping
    assert session.mux_mapping.groups[0] == ("4", "5", "6", "7")


def test_calib_session_hands_a_compatible_mapping_to_the_qubex_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapping = MuxMapping.from_groups(COMPATIBLE)
    session, orchestrator = _calib_session(monkeypatch, "qubex", mapping)

    session._initialize(["0"])

    assert orchestrator.call_args.kwargs["config"].mux_mapping is mapping
