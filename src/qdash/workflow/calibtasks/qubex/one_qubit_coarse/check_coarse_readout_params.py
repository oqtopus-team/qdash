from typing import ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckCoarseReadoutParams(QubexTask):
    """Task to check the Optimal Readout Frequency"""

    name: str = "CheckCoarseReadoutParams"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "readout_frequency": OutputParameterSpec(
            unit="GHz", description="Optimal Readout Frequency"
        ),
        "readout_amplitude": OutputParameterSpec(
            unit="a.u.", description="Optimal Readout Amplitude"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result
        self.output_parameters["readout_frequency"].value = result.data["optimal_readout_frequency"]
        self.output_parameters["readout_amplitude"].value = result.data["optimal_readout_amplitude"]
        output_parameters = self.attach_execution_id(execution_id)
        fig = result.figure
        figures = [fig]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        import qubex

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(backend, qid):
            result = qubex.contrib.characterize_coarse_readout_parameters(
                exp,
                target=label,
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
            )

        self.save_calibration(backend)
        return RunResult(raw_result=result)
