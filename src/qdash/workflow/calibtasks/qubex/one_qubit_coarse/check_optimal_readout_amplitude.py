from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL


class CheckOptimalReadoutAmplitude(QubexTask):
    """Task to check the Optimal Readout Amplitude"""

    name: str = "CheckOptimalReadoutAmplitude"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "amplitude_range": RunParameterModel(
            unit="a.u.",
            value_type="np.arange",
            value=(0.01, 0.25, 0.01),
            description="Readout amplitude range",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "readout_amplitude": ParameterModel(unit="a.u.", description="Optimal Readout Amplitude"),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result
        label = self.get_qubit_label(backend, qid)
        self.output_parameters["readout_amplitude"].value = result["optimal_amplitude"]
        output_parameters = self.attach_execution_id(execution_id)
        fig1 = result.figures["readout_fidelity"]
        fig2 = result.figures[f"{label}_prepared_0"]
        fig3 = result.figures[f"{label}_prepared_1"]
        figures = [fig1, fig2, fig3]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(backend, qid):
            result = exp.find_optimal_readout_amplitude(
                target=label,
                amplitude_range=self.run_parameters["amplitude_range"].get_value(),
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
            )

        self.save_calibration(backend)
        return RunResult(raw_result=result)
