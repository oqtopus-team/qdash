from collections.abc import Mapping
from importlib import import_module
from typing import Any, ClassVar

from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import RunParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import CheckQubitSpectroscopy
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckSimultaneousQubitSpectroscopy(CheckQubitSpectroscopy):
    """Task to run qubit spectroscopy for multiple qubits simultaneously."""

    name: str = "CheckSimultaneousQubitSpectroscopy"
    timeout: int = 60 * 120
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        **CheckQubitSpectroscopy.run_parameters,
        "power_range": RunParameterModel(
            unit="dB",
            value_type="np.arange",
            value=(-40.0, 1.0, 1.0),
            description="Drive power sweep range for simultaneous qubit spectroscopy",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=1024,
            description="Number of shots for simultaneous qubit spectroscopy",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Measurement interval for simultaneous qubit spectroscopy",
        ),
    }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run simultaneous qubit spectroscopy for one qubit.

        The single-qubit path still uses the contrib helper so task behavior is
        consistent with batch execution and fails early when qubex lacks the API.
        """
        return self.batch_run(backend, [qid])

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run simultaneous qubit spectroscopy for a batch of qubits."""
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]

        helper = self._load_simultaneous_qubit_spectroscopy()
        single_target = len(labels) == 1
        readout_amplitudes = None
        readout_frequencies = None
        if single_target:
            readout_amplitudes = {labels[0]: self._get_readout_amplitude_value()}
            readout_freq_param = self.input_parameters.get("readout_frequency")
            if readout_freq_param is not None:
                readout_frequencies = {labels[0]: readout_freq_param.value}

        raw_result = helper(
            exp,
            targets=labels,
            frequency_range=self._select_frequency_range(backend),
            power_range=self.run_parameters["power_range"].get_value(),
            readout_amplitudes=readout_amplitudes,
            readout_frequencies=readout_frequencies,
            shots=self.run_parameters["shots"].get_value(),
            interval=self.run_parameters["interval"].get_value(),
        )

        self.save_calibration(backend)
        return RunResult(raw_result=self._normalize_results(raw_result, labels))

    @staticmethod
    def _load_simultaneous_qubit_spectroscopy() -> Any:
        """Load the contributed qubex simultaneous spectroscopy helper."""
        return import_module("qubex.contrib").simultaneous_qubit_spectroscopy

    @staticmethod
    def _normalize_results(raw_result: Any, labels: list[str]) -> dict[str, Any]:
        """Normalize contrib output to the label-keyed payload used by postprocess.

        qubex.contrib.simultaneous_qubit_spectroscopy returns the same
        label-keyed payload shape for both single-target and multi-target runs.
        """
        if isinstance(raw_result, Mapping):
            if all(label in raw_result for label in labels):
                return dict(raw_result)

        payload = getattr(raw_result, "data", None)
        if isinstance(payload, Mapping) and all(label in payload for label in labels):
            return dict(payload)

        raise ValueError("Simultaneous qubit spectroscopy result is not keyed by qubit label")
