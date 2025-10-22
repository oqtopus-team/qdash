from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckQubit(QubexTask):
    """Task to check the Qubit Rabi oscillation breifly."""

    name: str = "CheckQubit"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "time_range": InputParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 201, 4),
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "rabi_amplitude": OutputParameterModel(unit="a.u.", description="Rabi oscillation amplitude"),
        "rabi_frequency": OutputParameterModel(unit="MHz", description="Rabi oscillation frequency"),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        result = run_result.raw_result
        self.output_parameters["rabi_amplitude"].value = result.rabi_params[label].amplitude
        self.output_parameters["rabi_amplitude"].error = result.data[label].fit()["amplitude_err"]
        self.output_parameters["rabi_frequency"].value = result.rabi_params[label].frequency * 1000  # convert to MHz
        self.output_parameters["rabi_frequency"].error = result.data[label].fit()["frequency_err"] * 1000
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        raw_data = [result.data[label].data]
        r2 = result.rabi_params[label].r2
        if self.r2_is_lower_than_threshold(r2):
            raise ValueError(f"R^2 value of Rabi oscillation is too low: {r2}")
        return PostProcessResult(output_parameters=output_parameters, figures=figures, raw_data=raw_data)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        result = exp.check_rabi(
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
            targets=[label],
        )
        self.save_calibration(session)
        r2 = result.rabi_params[label].r2 if result.rabi_params else None
        return RunResult(raw_result=result, r2={qid: r2})

    def batch_run(self, session: QubexSession, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(session)
        labels = [self.get_qubit_label(session, qid) for qid in qids]
        results = exp.check_rabi(
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
            targets=labels,
        )
        return RunResult(raw_result=results)
