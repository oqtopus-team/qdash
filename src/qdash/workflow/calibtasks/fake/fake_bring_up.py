"""Seed a fake project with the simulated device's parameters."""

from typing import Any, ClassVar

import plotly.graph_objects as go

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, PreProcessResult, RunResult
from qdash.workflow.calibtasks.fake.base import FakeTask
from qdash.workflow.engine.backend.fake import FakeBackend


class FakeBringUp(FakeTask):
    """Publish the simulated device's qubit and readout parameters to calibration storage.

    The qubex tasks that run on the fake backend read their inputs from the calibration
    database exactly as they do on hardware, and a fresh fake project holds no values yet.
    This task stands in for the hardware bring-up (resonator and qubit spectroscopy, control
    amplitude search) that the simulator does not emulate: it writes the simulator's own
    frequencies and amplitudes once, after which the qubex chain (CheckChevron, CheckRabi,
    CreateHPIPulse, ...) resolves every required input.
    """

    name: str = "FakeBringUp"
    task_type: str = "qubit"
    timeout: int = 60

    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {}
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qubit_frequency": OutputParameterSpec(
            unit="GHz", description="Qubit frequency of the simulated device"
        ),
        "resonator_frequency": OutputParameterSpec(
            unit="GHz", description="Readout resonator frequency of the simulated device"
        ),
        "readout_frequency": OutputParameterSpec(
            unit="GHz", description="Readout frequency, equal to the resonator frequency"
        ),
        "readout_amplitude": OutputParameterSpec(
            unit="a.u.", description="Readout amplitude the simulator expects"
        ),
        "control_amplitude": OutputParameterSpec(
            unit="a.u.", description="Control amplitude the simulator expects"
        ),
    }

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Nothing to resolve: the seed task has no inputs."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Read the simulated device's parameters for one qubit."""
        exp: Any = backend.get_instance()
        if not getattr(exp, "is_fake_qubex", False):
            raise RuntimeError(f"{self.name} only runs on the fake backend")

        label = exp.get_qubit_label(int(qid))
        resonator_frequency = float(exp.get_target(exp.get_resonator_label(int(qid))).frequency)
        return RunResult(
            raw_result={
                "label": label,
                "qubit_frequency": float(exp.get_target(label).frequency),
                "resonator_frequency": resonator_frequency,
                "readout_frequency": resonator_frequency,
                "readout_amplitude": float(exp.control_params.get_readout_amplitude(label)),
                "control_amplitude": float(exp.control_params.get_control_amplitude(label)),
            }
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Publish the parameters and summarise them in one table figure."""
        result = run_result.raw_result
        for name in self.output_spec:
            self.output_parameters[name].value = result[name]
        output_parameters = self.attach_execution_id(execution_id)

        names = list(self.output_spec)
        fig = go.Figure(
            data=go.Table(
                header={"values": ["Parameter", "Value", "Unit"]},
                cells={
                    "values": [
                        names,
                        [f"{result[name]:.6g}" for name in names],
                        [self.output_spec[name].unit for name in names],
                    ]
                },
            )
        )
        fig.update_layout(
            title={"text": f"Fake bring-up : Q{qid} ({result['label']})", "x": 0.5},
            width=600,
            height=320,
        )
        return PostProcessResult(output_parameters=output_parameters, figures=[fig])
