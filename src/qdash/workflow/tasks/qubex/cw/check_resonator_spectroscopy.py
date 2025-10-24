from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask


class CheckResonatorSpectroscopy(QubexTask):
    """Task to check the resonator spectroscopy."""

    name: str = "CheckResonatorSpectroscopy"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "frequency_range": InputParameterModel(
            unit="GHz",
            value_type="np.arange",
            value=(9.75, 10.75, 0.002),
            description="Frequency range for resonator spectroscopy",
        ),
        "power_range": InputParameterModel(
            unit="dB",
            value_type="np.arange",
            value=(-60, 5, 5),
            description="Power range for resonator spectroscopy",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=1024,
            description="Number of shots for resonator spectroscopy",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result
        figures = [result["fig"]]
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        read_box = exp.experiment_system.get_readout_box_for_qubit(label)
        import numpy as np
        from qubex.backend import BoxType

        if read_box.type == BoxType.QUEL1SE_R8:
            frequency_range = np.arange(5.75, 6.75, 0.002)
        else:
            frequency_range = self.input_parameters["frequency_range"].get_value()
        result = exp.resonator_spectroscopy(
            target=label,
            frequency_range=frequency_range,
            power_range=self.input_parameters["power_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
        )
        self.save_calibration(session)
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(session)
        labels = [self.get_qubit_label(session, qid) for qid in qids]
        read_box = exp.experiment_system.get_readout_box_for_qubit(labels[0])
        import numpy as np
        from qubex.backend import BoxType

        if read_box.type == BoxType.QUEL1SE_R8:
            frequency_range = np.arange(5.75, 6.75, 0.002)
        else:
            frequency_range = self.input_parameters["frequency_range"].get_value()
        result = exp.resonator_spectroscopy(
            labels[0],
            frequency_range=frequency_range,
            power_range=self.input_parameters["power_range"].get_value(),
            shots=1024,
        )
        self.save_calibration(session)
        return RunResult(raw_result=result)
