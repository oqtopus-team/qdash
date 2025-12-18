from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.workflow.engine.calibration.task.types import TaskTypes

PEAKS_COUNT = 4
peak_positions = {
    0: 1,
    1: 3,
    2: 2,
    3: 0,
}


class CheckResonatorFrequencies(QubexTask):
    """Task to check the resonator frequencies."""

    name: str = "CheckResonatorFrequencies"
    task_type = TaskTypes.QUBIT
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "frequency_range": InputParameterModel(
            unit="GHz",
            value_type="np.arange",
            value=(9.75, 10.75, 0.002),
            description="Frequency range for resonator frequencies",
        )
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "coarse_resonator_frequency": OutputParameterModel(
            unit="GHz", description="Coarse resonator frequency"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result
        figures = [result["fig_phase"], result["fig_phase_diff"]]
        id_in_mux = int(qid) % 4
        coarse_resonator_frequency = 0
        if len(result["peaks"]) == PEAKS_COUNT:
            coarse_resonator_frequency = result["peaks"][peak_positions[id_in_mux]]
        self.output_parameters["coarse_resonator_frequency"].value = coarse_resonator_frequency
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = exp.scan_resonator_frequencies(
            target=label, frequency_range=self.input_parameters["frequency_range"].get_value()
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        read_box = exp.experiment_system.get_readout_box_for_qubit(labels[0])
        import numpy as np
        from qubex.backend import BoxType

        if read_box.type == BoxType.QUEL1SE_R8:
            frequency_range = np.arange(5.75, 6.75, 0.002)
        else:
            frequency_range = self.input_parameters["frequency_range"].get_value()
        result = exp.scan_resonator_frequencies(
            labels[0],
            frequency_range=frequency_range,
            shots=1024,
            filter="savgol",
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
