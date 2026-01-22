import copy
import logging
from typing import TYPE_CHECKING, ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.analysis import (
    EstimateResonatorFrequencyConfig,
    estimate_and_mark_figure,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend

if TYPE_CHECKING:
    import plotly.graph_objs as go

logger = logging.getLogger(__name__)

# Number of resonators expected per mux
NUM_RESONATORS = 4

# Mapping from qubit position in mux (qid % 4) to resonance index
# This mapping reflects the physical arrangement of resonators
PEAK_POSITIONS = {
    0: 1,
    1: 3,
    2: 2,
    3: 0,
}


class CheckResonatorSpectroscopy(QubexTask):
    """Task to check the resonator spectroscopy.

    This is a MUX-level task that performs spectroscopy on all resonators
    in a MUX simultaneously. The scheduler should execute this task once
    per MUX, and the result will be used by all qubits in that MUX.

    Note: task_type remains "qubit" for frontend compatibility, but
    is_mux_level=True indicates this task runs once per MUX.
    """

    name: str = "CheckResonatorSpectroscopy"
    task_type: str = "qubit"
    is_mux_level: bool = True
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "frequency_range": RunParameterModel(
            unit="GHz",
            value_type="np.arange",
            value=(9.75, 10.75, 0.002),
            description="Frequency range for resonator spectroscopy",
        ),
        "power_range": RunParameterModel(
            unit="dB",
            value_type="np.arange",
            value=(-60, 5, 5),
            description="Power range for resonator spectroscopy",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=1024,
            description="Number of shots for resonator spectroscopy",
        ),
        "num_resonators": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=NUM_RESONATORS,
            description="Number of resonators to detect",
        ),
        "high_power_min": RunParameterModel(
            unit="dB",
            value_type="float",
            value=-20.0,
            description="Minimum power for high-power peak detection",
        ),
        "high_power_max": RunParameterModel(
            unit="dB",
            value_type="float",
            value=0.0,
            description="Maximum power for high-power peak detection",
        ),
        "low_power": RunParameterModel(
            unit="dB",
            value_type="float",
            value=-30.0,
            description="Power level for low-power peak detection",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "resonator_frequency": ParameterModel(
            unit="GHz", description="Estimated resonator frequency from spectroscopy"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task.

        Returns two figures:
        1. Raw figure (original spectroscopy data)
        2. Marked figure (with detected resonances annotated)

        This method can be called for any qid in the MUX, and it will extract
        the appropriate resonator frequency based on the qid's position in the MUX.
        """
        result = run_result.raw_result
        raw_fig: go.Figure = result["fig"]

        # Estimate resonator frequency and create marked figure
        estimated_frequency = 0.0
        marked_fig = None
        try:
            config = EstimateResonatorFrequencyConfig(
                num_resonators=self.run_parameters["num_resonators"].get_value(),
                high_power_min=self.run_parameters["high_power_min"].get_value(),
                high_power_max=self.run_parameters["high_power_max"].get_value(),
                low_power=self.run_parameters["low_power"].get_value(),
            )
            marked_fig, _, frequencies = estimate_and_mark_figure(raw_fig, config)

            if len(frequencies) == NUM_RESONATORS:
                # Get frequency for current qid based on its position in the MUX
                id_in_mux = int(qid) % 4
                resonance_index = PEAK_POSITIONS[id_in_mux]
                estimated_frequency = frequencies[resonance_index]
                print(f"[MUX DEBUG] qid={qid}, id_in_mux={id_in_mux}, resonance_index={resonance_index}, frequency={estimated_frequency}, all_frequencies={frequencies}")
        except Exception:
            logger.warning(
                "Failed to estimate resonator frequency for qid=%s",
                qid,
                exc_info=True,
            )

        # Return both raw and marked figures
        figures: list[go.Figure] = [raw_fig]
        if marked_fig is not None:
            figures.append(marked_fig)

        # Create a deep copy of output_parameters to avoid sharing state
        # between multiple qids (output_parameters is a ClassVar)
        output_params_copy = copy.deepcopy(self.output_parameters)
        output_params_copy["resonator_frequency"].value = estimated_frequency
        for value in output_params_copy.values():
            value.execution_id = execution_id

        return PostProcessResult(
            output_parameters=output_params_copy,
            figures=figures,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        read_box = exp.experiment_system.get_readout_box_for_qubit(label)
        import numpy as np
        from qubex.backend import BoxType

        if read_box.type == BoxType.QUEL1SE_R8:
            frequency_range = np.arange(5.75, 6.75, 0.002)
        else:
            frequency_range = self.run_parameters["frequency_range"].get_value()
        result = exp.resonator_spectroscopy(
            target=label,
            frequency_range=frequency_range,
            power_range=self.run_parameters["power_range"].get_value(),
            shots=self.run_parameters["shots"].get_value(),
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
            frequency_range = self.run_parameters["frequency_range"].get_value()
        result = exp.resonator_spectroscopy(
            labels[0],
            frequency_range=frequency_range,
            power_range=self.run_parameters["power_range"].get_value(),
            shots=1024,
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
