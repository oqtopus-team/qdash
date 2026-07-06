from typing import ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.calibtasks.qubex.validation import finite_value_error
from qdash.workflow.engine.backend.qubex import QubexBackend


class CreateHPIPulse(QubexTask):
    """Task to create the HPI pulse."""

    name: str = "CreateHPIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": None,  # Load from DB
        "control_amplitude": None,  # Load from DB
        "readout_amplitude": None,  # Load from DB
        "readout_frequency": None,  # Load from DB
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION, unit="ns", description="Readout pulse length"
        ),
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "hpi_duration": RunParameterModel(
            unit="ns", value_type="int", value=HPI_DURATION, description="HPI pulse length"
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for calibration",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for calibration",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "hpi_amplitude": ParameterModel(unit="", description="HPI pulse amplitude"),
        "hpi_length": ParameterModel(value=HPI_DURATION, unit="ns", description="HPI pulse length"),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["hpi_amplitude"].value = result.data[label].calib_value
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        validation_error = finite_value_error(
            self.output_parameters["hpi_amplitude"].value,
            f"CreateHPIPulse hpi_amplitude for {label}",
            minimum=0.0,
            maximum=1.0,
        )
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            validation_error=validation_error,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[labels[0]] = readout_amp_param.value
        control_amp_param = self.input_parameters["control_amplitude"]
        if control_amp_param is not None:
            exp.params.control_amplitude[labels[0]] = control_amp_param.value
        result = exp.calibrate_hpi_pulse(
            targets=labels,
            n_rotations=1,
            duration=self.run_parameters["hpi_duration"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})
