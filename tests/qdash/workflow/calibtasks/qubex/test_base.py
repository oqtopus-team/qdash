"""Tests for QubexTask._load_parameters_from_db."""

from typing import Any
from unittest.mock import MagicMock, patch

from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask


class ConcreteQubexTask(QubexTask):
    """Concrete subclass of QubexTask for testing."""

    name: str = "TestTask"

    def run(self, backend: Any, qid: str) -> RunResult:
        return RunResult(output_parameters={})

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

        assert task.input_parameters["control_qubit_frequency"].value == 5.2

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

        assert task.input_parameters["qubit_frequency"].value == 4.8


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
        coupling_data: dict = {}

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

        assert task.input_parameters["control_qubit_frequency"].value == 5.0

    def test_target_qubit_param_loaded_from_qubit_document(self):
        """For qid_role='target', parameter should be loaded from target qubit's
        QubitDocument using parameter_name."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "target_qubit_frequency": ParameterModel(
                parameter_name="qubit_frequency", qid_role="target", unit="GHz"
            ),
        }

        control_qubit_data: dict = {}
        target_qubit_data = {
            "qubit_frequency": {"value": 6.5, "unit": "GHz"},
        }
        coupling_data: dict = {}

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

        assert task.input_parameters["target_qubit_frequency"].value == 6.5

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
        control_qubit_data: dict = {}
        target_qubit_data: dict = {}
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

        assert task.input_parameters["cr_amplitude"].value == 0.45

    def test_coupling_role_param_loaded_from_coupling_document(self):
        """For qid_role='coupling', parameter should be loaded directly from
        CouplingDocument."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "zx_rotation_rate": ParameterModel(
                parameter_name="zx_rotation_rate", qid_role="coupling", unit="a.u."
            ),
        }

        control_qubit_data: dict = {}
        target_qubit_data: dict = {}
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

        assert task.input_parameters["zx_rotation_rate"].value == 1.23

    def test_parameter_not_found_creates_empty_parameter_model(self):
        """When a parameter (with value None) is not found in any source,
        an empty ParameterModel with description should be created."""
        task = ConcreteQubexTask()
        task.input_parameters = {
            "missing_param": None,
        }

        control_qubit_data: dict = {}
        target_qubit_data: dict = {}
        coupling_data: dict = {}

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

        assert task.input_parameters["control_qubit_frequency"].value == 5.0
        assert task.input_parameters["target_qubit_frequency"].value == 6.0
        assert task.input_parameters["zx_rotation_rate"].value == 1.5
        assert task.input_parameters["cr_amplitude"].value == 0.3
