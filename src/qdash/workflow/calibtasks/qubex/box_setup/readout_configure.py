from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class ReadoutConfigure(QubexTask):
    """Task to configure the box."""

    name: str = "ReadoutConfigure"
    task_type: str = "global"
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "qubits": RunParameterModel(
            unit="a.u.",
            value_type="list",
            value=[],
            description="List of muxes to check skew",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(output_parameters={})

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)

        def readout_configure() -> RunResult | None:
            import numpy as np

            sys = exp.config_loader.get_experiment_system(chip_id=exp.chip_id)
            qubits = self.run_parameters["qubits"].get_value()
            if len(qubits) == 0:
                return RunResult(raw_result=None)
            qubits = [exp.get_qubit_label(int(qid)) for qid in qubits]
            for r in sys.resonators:
                if r.qubit not in qubits:
                    r.frequency = np.nan  # Update readout only
            exp.system_manager.set_experiment_system(sys)
            exp.system_manager.experiment_system.configure()
            exp.system_manager.push(
                exp.box_ids, confirm=False
            )  # Use config values for control, update box linked to specified qubit's readout
            return None

        readout_configure()

        return RunResult(raw_result=None)
