from typing import Any, cast

from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.base import PreProcessResult
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_fine_chevron import (
    CheckFineChevron,
)
from qdash.workflow.engine.backend.fake import FakeBackend


class FakeCheckFineChevron(CheckFineChevron):
    """Fake-backend adapter for the production CheckFineChevron task.

    The production task expects initial qubit/readout frequencies from calibration
    storage. A fresh fake project has no stored calibration yet, so seed those
    inputs from FakeExperiment while keeping the production task implementation
    unchanged.
    """

    backend = "fake"
    name = "CheckFineChevron"

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        result = super().preprocess(cast("Any", backend), qid)
        self._seed_fake_frequency_inputs(backend, qid)
        return result

    def run(self, backend: FakeBackend, qid: str) -> Any:
        self._seed_fake_frequency_inputs(backend, qid)
        return super().run(cast("Any", backend), qid)

    def _seed_fake_frequency_inputs(self, backend: FakeBackend, qid: str) -> None:
        exp = backend.get_instance()
        if not getattr(exp, "is_fake_qubex", False):
            return

        label = exp.get_qubit_label(int(qid))
        resonator_label = exp.get_resonator_label(int(qid))
        defaults = {
            "qubit_frequency": (
                float(exp.qubit_frequencies[exp.qubit_labels.index(label)]),
                "GHz",
                "Fake default qubit frequency",
            ),
            "readout_frequency": (
                float(exp.readout_frequencies[exp.resonator_labels.index(resonator_label)]),
                "GHz",
                "Fake default readout frequency",
            ),
        }
        for name, (value, unit, description) in defaults.items():
            param = self.input_parameters.get(name)
            if param is None:
                self.input_parameters[name] = ParameterModel(
                    value=value,
                    unit=unit,
                    description=description,
                )
                continue
            current = getattr(param, "value", None)
            if current is None or float(current) < 3.0:
                param.value = value
                param.unit = param.unit or unit
                param.description = param.description or description
