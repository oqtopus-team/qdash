from typing import Any, ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckWaveform(QubexTask):
    """Task to check readout waveforms."""

    name: str = "CheckWaveform"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for waveform measurement",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Shot interval for waveform measurement",
        ),
        "readout_amplitude": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=None,
            description="Readout pulse amplitude. Uses qubex default when unset.",
        ),
        "readout_duration": RunParameterModel(
            unit="ns",
            value_type="float",
            value=None,
            description="Readout pulse duration. Uses qubex default when unset.",
        ),
        "readout_pre_margin": RunParameterModel(
            unit="ns",
            value_type="float",
            value=None,
            description="Readout pre-margin. Uses qubex default when unset.",
        ),
        "readout_post_margin": RunParameterModel(
            unit="ns",
            value_type="float",
            value=None,
            description="Readout post-margin. Uses qubex default when unset.",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {}

    def _optional_run_parameter(self, name: str) -> Any:
        parameter = self.run_parameters[name]
        if parameter.value is None:
            return None
        return parameter.get_value()

    def _check_waveform(self, backend: QubexBackend, targets: str | list[str]) -> Any:
        exp = self.get_experiment(backend)
        return exp.check_waveform(
            targets=targets,
            n_shots=self._optional_run_parameter("shots"),
            shot_interval=self._optional_run_parameter("interval"),
            readout_amplitude=self._optional_run_parameter("readout_amplitude"),
            readout_duration=self._optional_run_parameter("readout_duration"),
            readout_pre_margin=self._optional_run_parameter("readout_pre_margin"),
            readout_post_margin=self._optional_run_parameter("readout_post_margin"),
        )

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the waveform check result."""
        label = self.get_qubit_label(backend, qid)
        data = getattr(run_result.raw_result, "data", {})
        figure = None
        if label in data and hasattr(data[label], "plot"):
            figure = data[label].plot(return_figure=True)
        figures = [figure] if figure is not None else []
        return PostProcessResult(output_parameters={}, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        label = self.get_qubit_label(backend, qid)
        result = self._check_waveform(backend, label)
        self.save_calibration(backend)
        return RunResult(raw_result=result)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        result = self._check_waveform(backend, labels)
        self.save_calibration(backend)
        return RunResult(raw_result=result)
