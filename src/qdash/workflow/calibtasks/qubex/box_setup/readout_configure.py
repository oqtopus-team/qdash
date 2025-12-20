from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel, TaskTypes
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class ReadoutConfigure(QubexTask):
    """Task to configure the box."""

    name: str = "ReadoutConfigure"
    task_type = TaskTypes.GLOBAL
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "qubits": InputParameterModel(
            unit="a.u.",
            value_type="list",
            value=[],
            description="List of muxes to check skew",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(output_parameters={})

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)

        def readout_configure() -> RunResult | None:
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
            return None

        readout_configure()

        return RunResult(raw_result=None)
