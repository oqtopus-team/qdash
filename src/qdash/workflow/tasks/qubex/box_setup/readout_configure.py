from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class ReadoutConfigure(BaseTask):
    """Task to configure the box."""

    name: str = "ReadoutConfigure"
    backend: str = "qubex"
    task_type: str = "global"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "qubits": InputParameterModel(
            unit="a.u.",
            value_type="list",
            value=[],
            description="List of muxes to check skew",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        pass

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        pass

    def run(self, session: QubexSession, qid: str) -> RunResult:  # noqa: ARG002
        exp = session.get_session()

        def readout_configure():
            import numpy as np

            sys = exp.config_loader.get_experiment_system(chip_id=exp.chip_id)
            qubits = self.input_parameters["qubits"].get_value()
            if len(qubits) == 0:
                return RunResult(raw_result=None)
            qubits = [exp.get_qubit_label(int(qid)) for qid in qubits]
            for r in sys.resonators:
                if r.qubit not in qubits:
                    r.frequency = np.nan  # readoutだけ更新
            exp.system_manager.set_experiment_system(sys)
            exp.system_manager.experiment_system.configure()
            exp.system_manager.push(
                exp.box_ids, confirm=False
            )  # controlはconfigの値でreadoutは指定した量子ビットのreadoutが紐づいているboxを更新

        readout_configure()

        return RunResult(raw_result=None)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(f"Batch run is not implemented for {self.name} task. Use run method instead.")
