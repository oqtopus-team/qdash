"""Tests for QubexTask._load_parameters_from_db."""

from typing import Any, ClassVar, cast
from unittest.mock import MagicMock, patch

import pytest

from qdash.datamodel.task import InputParameterSpec, ParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask


class ConcreteQubexTask(QubexTask):
    """Concrete subclass of QubexTask for testing."""

    name: str = "TestTask"
    task_type: str = "qubit"

    def run(self, backend: Any, qid: str) -> RunResult:
        return RunResult(raw_result={})

    def postprocess(self, backend: Any, qid: str, result: RunResult) -> None:
        pass


def _make_backend(project_id: str = "proj1", chip_id: str = "chip1") -> MagicMock:
    """Create a mock QubexBackend with config."""
    backend = MagicMock()
    backend.config = {"project_id": project_id, "chip_id": chip_id}
    return backend


class TestLoadParametersFromDbQubitTask:
    """Test _load_parameters_from_db for single-qubit tasks."""

    def test_qubit_task_uses_parameter_name_as_lookup_key(self):
        """When parameter_name is set, it should be used as the DB lookup key
        instead of the dict key."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "control_qubit_frequency": ParameterModel(
                parameter_name="qubit_frequency", qid_role="", unit="GHz"
            ),
        }

        qubit_data = {
            "qubit_frequency": {"value": 5.2, "unit": "GHz", "description": "Qubit freq"},
        }

        backend = _make_backend()
        with patch(
            "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
        ) as MockQubitRepo:
            MockQubitRepo.return_value.get_calibration_data.return_value = qubit_data
            task._load_parameters_from_db(backend, "0")

        param = task.input_parameters["control_qubit_frequency"]
        assert param is not None
        assert param.value == 5.2

    def test_qubit_task_falls_back_to_dict_key_when_no_parameter_name(self):
        """When parameter_name is empty, dict key is used as lookup."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "qubit_frequency": ParameterModel(unit="GHz"),
        }

        qubit_data = {
            "qubit_frequency": {"value": 4.8, "unit": "GHz"},
        }

        backend = _make_backend()
        with patch(
            "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
        ) as MockQubitRepo:
            MockQubitRepo.return_value.get_calibration_data.return_value = qubit_data
            task._load_parameters_from_db(backend, "0")

        param = task.input_parameters["qubit_frequency"]
        assert param is not None
        assert param.value == 4.8

    def test_explicit_required_resolution_fails_without_database_value(self):
        class RequiredInputTask(ConcreteQubexTask):
            input_spec: ClassVar[dict[str, InputParameterSpec]] = {
                "frequency": InputParameterSpec(
                    resolution="database_required",
                    user_override="allowed",
                    default=None,
                )
            }

        task = RequiredInputTask()
        with patch(
            "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
        ) as mock_repo:
            mock_repo.return_value.get_calibration_data.return_value = {}
            with pytest.raises(ValueError, match="Required input parameter 'frequency'"):
                task._load_parameters_from_db(_make_backend(), "0")

    def test_database_or_default_uses_explicit_default(self):
        class DefaultInputTask(ConcreteQubexTask):
            input_spec: ClassVar[dict[str, InputParameterSpec]] = {
                "amplitude": InputParameterSpec(
                    resolution="database_or_default",
                    user_override="allowed",
                    default=0.25,
                    unit="a.u.",
                )
            }

        task = DefaultInputTask()
        with patch(
            "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
        ) as mock_repo:
            mock_repo.return_value.get_calibration_data.return_value = {}
            task._load_parameters_from_db(_make_backend(), "0")

        assert task.input_parameters["amplitude"].value == 0.25

    def test_default_only_ignores_database_value(self):
        class FixedInputTask(ConcreteQubexTask):
            input_spec: ClassVar[dict[str, InputParameterSpec]] = {
                "length": InputParameterSpec(
                    resolution="default_only",
                    user_override="forbidden",
                    default=100,
                    unit="ns",
                )
            }

        task = FixedInputTask()
        with patch(
            "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
        ) as mock_repo:
            mock_repo.return_value.get_calibration_data.return_value = {"length": {"value": 200}}
            task._load_parameters_from_db(_make_backend(), "0")

        assert task.input_parameters["length"].value == 100

    def test_preprocess_does_not_reload_database_after_snapshot_resolution(self):
        task = ConcreteQubexTask()
        task.input_parameters = {"frequency": ParameterModel(value=5.1, unit="GHz")}
        task.input_parameters_from_snapshot = True

        with patch(
            "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
        ) as mock_repo:
            result = task.preprocess(_make_backend(), "0")

        mock_repo.assert_not_called()
        assert result.input_parameters["frequency"].value == 5.1


class TestLoadParametersFromDbCouplingTask:
    """Test _load_parameters_from_db for coupling tasks."""

    def test_control_qubit_param_loaded_from_qubit_document(self):
        """For qid_role='control', parameter should be loaded from control qubit's
        QubitDocument using parameter_name as the lookup key."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "control_qubit_frequency": ParameterModel(
                parameter_name="qubit_frequency", qid_role="control", unit="GHz"
            ),
        }

        control_qubit_data = {
            "qubit_frequency": {"value": 5.0, "unit": "GHz"},
        }
        target_qubit_data = {
            "qubit_frequency": {"value": 6.0, "unit": "GHz"},
        }
        coupling_data: dict[str, Any] = {}

        backend = _make_backend()
        with (
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
            ) as MockQubitRepo,
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoCouplingCalibrationRepository"
            ) as MockCouplingRepo,
        ):
            qubit_repo = MockQubitRepo.return_value
            qubit_repo.get_calibration_data.side_effect = [
                control_qubit_data,
                target_qubit_data,
            ]
            MockCouplingRepo.return_value.get_calibration_data.return_value = coupling_data

            task._load_parameters_from_db(backend, "0-1")

        param = task.input_parameters["control_qubit_frequency"]
        assert param is not None
        assert param.value == 5.0

    def test_target_qubit_param_loaded_from_qubit_document(self):
        """For qid_role='target', parameter should be loaded from target qubit's
        QubitDocument using parameter_name."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "target_qubit_frequency": ParameterModel(
                parameter_name="qubit_frequency", qid_role="target", unit="GHz"
            ),
        }

        control_qubit_data: dict[str, Any] = {}
        target_qubit_data = {
            "qubit_frequency": {"value": 6.5, "unit": "GHz"},
        }
        coupling_data: dict[str, Any] = {}

        backend = _make_backend()
        with (
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
            ) as MockQubitRepo,
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoCouplingCalibrationRepository"
            ) as MockCouplingRepo,
        ):
            qubit_repo = MockQubitRepo.return_value
            qubit_repo.get_calibration_data.side_effect = [
                control_qubit_data,
                target_qubit_data,
            ]
            MockCouplingRepo.return_value.get_calibration_data.return_value = coupling_data

            task._load_parameters_from_db(backend, "0-1")

        param = task.input_parameters["target_qubit_frequency"]
        assert param is not None
        assert param.value == 6.5

    def test_cr_amplitude_falls_back_to_coupling_document(self):
        """cr_amplitude has qid_role='control' but data lives in CouplingDocument.
        The fallback mechanism should find it there."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "cr_amplitude": ParameterModel(
                parameter_name="cr_amplitude", qid_role="control", unit="a.u."
            ),
        }

        # cr_amplitude is NOT in control qubit data
        control_qubit_data: dict[str, Any] = {}
        target_qubit_data: dict[str, Any] = {}
        # But IS in coupling data
        coupling_data = {
            "cr_amplitude": {"value": 0.45, "unit": "a.u."},
        }

        backend = _make_backend()
        with (
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
            ) as MockQubitRepo,
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoCouplingCalibrationRepository"
            ) as MockCouplingRepo,
        ):
            qubit_repo = MockQubitRepo.return_value
            qubit_repo.get_calibration_data.side_effect = [
                control_qubit_data,
                target_qubit_data,
            ]
            MockCouplingRepo.return_value.get_calibration_data.return_value = coupling_data

            task._load_parameters_from_db(backend, "0-1")

        param = task.input_parameters["cr_amplitude"]
        assert param is not None
        assert param.value == 0.45

    def test_coupling_role_param_loaded_from_coupling_document(self):
        """For qid_role='coupling', parameter should be loaded directly from
        CouplingDocument."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "zx_rotation_rate": ParameterModel(
                parameter_name="zx_rotation_rate", qid_role="coupling", unit="a.u."
            ),
        }

        control_qubit_data: dict[str, Any] = {}
        target_qubit_data: dict[str, Any] = {}
        coupling_data = {
            "zx_rotation_rate": {"value": 1.23, "unit": "a.u."},
        }

        backend = _make_backend()
        with (
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
            ) as MockQubitRepo,
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoCouplingCalibrationRepository"
            ) as MockCouplingRepo,
        ):
            qubit_repo = MockQubitRepo.return_value
            qubit_repo.get_calibration_data.side_effect = [
                control_qubit_data,
                target_qubit_data,
            ]
            MockCouplingRepo.return_value.get_calibration_data.return_value = coupling_data

            task._load_parameters_from_db(backend, "0-1")

        param = task.input_parameters["zx_rotation_rate"]
        assert param is not None
        assert param.value == 1.23

    def test_parameter_not_found_creates_empty_parameter_model(self):
        """Legacy None declarations retain their compatibility behavior."""
        task = ConcreteQubexTask()
        task.input_parameters = cast("Any", {"missing_param": None})

        control_qubit_data: dict[str, Any] = {}
        target_qubit_data: dict[str, Any] = {}
        coupling_data: dict[str, Any] = {}

        backend = _make_backend()
        with (
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
            ) as MockQubitRepo,
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoCouplingCalibrationRepository"
            ) as MockCouplingRepo,
        ):
            qubit_repo = MockQubitRepo.return_value
            qubit_repo.get_calibration_data.side_effect = [
                control_qubit_data,
                target_qubit_data,
            ]
            MockCouplingRepo.return_value.get_calibration_data.return_value = coupling_data

            task._load_parameters_from_db(backend, "0-1")

        result = task.input_parameters["missing_param"]
        assert isinstance(result, ParameterModel)
        assert "not found" in result.description

    def test_required_database_parameter_raises_when_missing(self):
        task = ConcreteQubexTask()
        task.input_parameters = {
            "missing_param": ParameterModel(source="database", required=True, value=None),
        }

        backend = _make_backend()
        with (
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
            ) as mock_qubit_repo,
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoCouplingCalibrationRepository"
            ) as mock_coupling_repo,
        ):
            mock_qubit_repo.return_value.get_calibration_data.side_effect = [{}, {}]
            mock_coupling_repo.return_value.get_calibration_data.return_value = {}

            with pytest.raises(ValueError, match="Required input parameter 'missing_param'"):
                task._load_parameters_from_db(backend, "0-1")

    def test_mixed_parameters_from_multiple_sources(self):
        """A coupling task with parameters from all three sources should load
        each from the correct source."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "control_qubit_frequency": ParameterModel(
                parameter_name="qubit_frequency", qid_role="control", unit="GHz"
            ),
            "target_qubit_frequency": ParameterModel(
                parameter_name="qubit_frequency", qid_role="target", unit="GHz"
            ),
            "zx_rotation_rate": ParameterModel(
                parameter_name="zx_rotation_rate", qid_role="coupling", unit="a.u."
            ),
            "cr_amplitude": ParameterModel(
                parameter_name="cr_amplitude", qid_role="control", unit="a.u."
            ),
        }

        control_qubit_data = {"qubit_frequency": {"value": 5.0}}
        target_qubit_data = {"qubit_frequency": {"value": 6.0}}
        coupling_data = {
            "zx_rotation_rate": {"value": 1.5},
            "cr_amplitude": {"value": 0.3},
        }

        backend = _make_backend()
        with (
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoQubitCalibrationRepository"
            ) as MockQubitRepo,
            patch(
                "qdash.workflow.calibtasks.qubex.base.MongoCouplingCalibrationRepository"
            ) as MockCouplingRepo,
        ):
            qubit_repo = MockQubitRepo.return_value
            qubit_repo.get_calibration_data.side_effect = [
                control_qubit_data,
                target_qubit_data,
            ]
            MockCouplingRepo.return_value.get_calibration_data.return_value = coupling_data

            task._load_parameters_from_db(backend, "0-1")

        p1 = task.input_parameters["control_qubit_frequency"]
        assert p1 is not None
        assert p1.value == 5.0
        p2 = task.input_parameters["target_qubit_frequency"]
        assert p2 is not None
        assert p2.value == 6.0
        p3 = task.input_parameters["zx_rotation_rate"]
        assert p3 is not None
        assert p3.value == 1.5
        p4 = task.input_parameters["cr_amplitude"]
        assert p4 is not None
        assert p4.value == 0.3
