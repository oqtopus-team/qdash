"""Configuration tasks preserve readout isolation and select usable EF channels."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.qubex.box_setup.configure import Configure, ConfigureEF
from qdash.workflow.calibtasks.qubex.validation import require_ef_configuration
from qdash.workflow.engine.backend.qubex import QubexBackend


class ConfigurationExperiment:
    def __init__(self, *, ef_available: bool = True) -> None:
        self.ctx = SimpleNamespace(
            _configuration_mode="ge-cr-cr",
            resolve_ge_label=lambda label: f"{label}_ge",
            resolve_ef_label=lambda label: f"{label}_ef",
        )
        self.chip_id = "chip"
        self.config_path = "/config"
        self.params_path = "/params"
        self.box_ids = ["box-1"]
        self.calib_note = MagicMock()
        self.ef_available = ef_available
        self.system_manager = MagicMock()
        self.system_manager.load.side_effect = self._load
        self.targets: dict[str, Any] = {}
        for label, port_id in [("R00", "read:0"), ("R01", "read:0"), ("R04", "read:1")]:
            self.targets[label] = SimpleNamespace(
                label=label, channel=SimpleNamespace(port=SimpleNamespace(id=port_id))
            )
        self.experiment_system = SimpleNamespace(read_out_targets=list(self.targets.values()))
        self.targets["Q00_ge"] = SimpleNamespace(channel=SimpleNamespace(id="ctrl:0"))

    @property
    def configuration_mode(self) -> str:
        return str(self.ctx._configuration_mode)

    def _load(self, **kwargs: Any) -> None:
        self.targets.pop("Q00_ef", None)
        if self.ef_available and kwargs["configuration_mode"] in ("ge-ef-cr", "ge-ef-fh"):
            self.targets["Q00_ef"] = SimpleNamespace(channel=SimpleNamespace(id="ctrl:1"))

    def get_qubit_label(self, qid: int) -> str:
        return f"Q{qid:02d}"

    def get_resonator_label(self, qid: int) -> str:
        return f"R{qid:02d}"


def _backend(exp: Any) -> QubexBackend:
    backend = QubexBackend({})
    backend._exp = exp
    return backend


@pytest.mark.parametrize("initial_mode", ["ge-cr-cr", "ge-ef-fh"])
@pytest.mark.parametrize("old_snapshot", [False, True])
def test_configure_ef_then_configure_uses_cr_mode_and_preserves_readout_isolation(
    initial_mode: str, old_snapshot: bool
) -> None:
    exp = ConfigurationExperiment()
    exp.ctx._configuration_mode = initial_mode
    backend = _backend(exp)
    task = generate_task_instances(["ConfigureEF"], {"ConfigureEF": {}}, "qubex")["ConfigureEF"]

    result = task.run(backend, "0")
    require_ef_configuration(cast("Any", exp), "Q00")
    configure = Configure()
    if old_snapshot:
        configure.run_parameters.clear()
    configure.run(backend, "0")

    assert result.raw_result is None
    assert exp.configuration_mode == initial_mode
    assert backend.config == {}
    assert exp.system_manager.load.call_count == 2
    for call, mode in zip(
        exp.system_manager.load.call_args_list, ["ge-ef-cr", "ge-cr-cr"], strict=True
    ):
        assert call.kwargs == {
            "chip_id": "chip",
            "config_dir": "/config",
            "params_dir": "/params",
            "targets_to_exclude": ["R01"],
            "configuration_mode": mode,
        }
    exp.system_manager.push.assert_called_with(box_ids=["box-1"], confirm=False, parallel=False)
    assert exp.calib_note.save.call_count == 2


def test_configure_can_explicitly_restore_cr_mode() -> None:
    exp = ConfigurationExperiment()
    backend = _backend(exp)
    ConfigureEF().run(backend, "0")
    task = Configure({"run_parameters": {"configuration_mode": {"value": "ge-cr-cr"}}})

    task.run(backend, "0")

    assert exp.configuration_mode == "ge-cr-cr"
    assert backend.config == {}
    assert "Q00_ef" not in exp.targets


@pytest.mark.parametrize("old_snapshot", [False, True])
def test_configure_uses_cr_mode_by_default(old_snapshot: bool) -> None:
    exp = ConfigurationExperiment()
    exp.ctx._configuration_mode = "ge-ef-fh"
    task = Configure()
    if old_snapshot:
        task.run_parameters.clear()

    task.run(_backend(exp), "0")

    assert exp.system_manager.load.call_args.kwargs["configuration_mode"] == "ge-cr-cr"


@pytest.mark.parametrize("task_type", [Configure, ConfigureEF])
def test_unsupported_mode_is_rejected_before_loading(task_type: type[Configure]) -> None:
    exp = ConfigurationExperiment()
    task = task_type({"run_parameters": {"configuration_mode": {"value": "invalid"}}})

    with pytest.raises(ValueError, match="configuration_mode"):
        task.run(_backend(exp), "0")

    exp.system_manager.load.assert_not_called()
    exp.system_manager.push.assert_not_called()


def test_configure_ef_rejects_cr_only_mode() -> None:
    task = ConfigureEF({"run_parameters": {"configuration_mode": {"value": "ge-cr-cr"}}})
    with pytest.raises(ValueError, match="ConfigureEF requires"):
        task.run(_backend(ConfigurationExperiment()), "0")


@pytest.mark.parametrize("task_type", [Configure, ConfigureEF])
@pytest.mark.parametrize("mode", ["ge-ef-cr", "ge-ef-fh"])
def test_configuration_does_not_require_ef_measurement_channels(
    task_type: type[Configure], mode: str
) -> None:
    exp = ConfigurationExperiment(ef_available=False)
    backend = _backend(exp)
    task = task_type({"run_parameters": {"configuration_mode": {"value": mode}}})

    task.run(backend, "0")

    assert exp.system_manager.load.call_args.kwargs["configuration_mode"] == mode
    exp.system_manager.push.assert_called_once_with(
        box_ids=["box-1"], confirm=False, parallel=False
    )
    exp.calib_note.save.assert_called_once_with()
    assert exp.configuration_mode == "ge-cr-cr"


def test_push_failure_does_not_save_calibration() -> None:
    exp = ConfigurationExperiment()
    backend = _backend(exp)
    exp.system_manager.push.side_effect = RuntimeError("push failed")

    with pytest.raises(RuntimeError, match="push failed"):
        ConfigureEF().run(backend, "0")

    assert exp.configuration_mode == "ge-cr-cr"
    assert "configuration_mode" not in backend.config
    exp.calib_note.save.assert_not_called()
