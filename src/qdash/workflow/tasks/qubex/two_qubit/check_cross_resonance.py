from typing import ClassVar

import numpy as np
import plotly.graph_objects as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckCrossResonance(BaseTask):
    """Task to check the cross resonance pulse."""

    name: str = "CheckCrossResonance"
    backend: str = "qubex"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "cr_amplitude": OutputParameterModel(
            unit="a.u.", value_type="float", description="Amplitude of the CR pulse."
        ),
        "cr_phase": OutputParameterModel(
            unit="a.u.", value_type="float", description="Phase of the CR pulse."
        ),
        "cancel_amplitude": OutputParameterModel(
            unit="a.u.", value_type="float", description="Amplitude of the cancel pulse."
        ),
        "cancel_phase": OutputParameterModel(
            unit="a.u.", value_type="float", description="Phase of the cancel pulse."
        ),
        "cancel_beta": OutputParameterModel(
            unit="a.u.", value_type="float", description="Beta of the cancel pulse."
        ),
        "rotary_amplitude": OutputParameterModel(
            unit="a.u.", value_type="float", description="Amplitude of the rotary pulse."
        ),
        "zx_rotation_rate": OutputParameterModel(
            unit="a.u.", value_type="float", description="ZX rotation rate."
        ),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def _plot_coeffs_history(self, coeffs_history: dict, label: str) -> go.Figure:
        fig = go.Figure()
        for key, value in coeffs_history.items():
            fig.add_trace(
                go.Scatter(
                    x=np.arange(1, len(value) + 1),
                    y=value * 1e3,
                    mode="lines+markers",
                    name=f"{key}/2",
                )
            )
        fig.update_layout(
            title=f"CR Hamiltonian coefficients : {label}",
            xaxis_title="Number of steps",
            yaxis_title="Coefficient (MHz)",
            xaxis={"tickmode": "array", "tickvals": np.arange(len(value))},
        )
        return fig

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = session.get_session()
        label = "-".join(
            [exp.get_qubit_label(int(q)) for q in qid.split("-")]
        )  # e.g., "0-1" → "Q00-Q01"
        result = run_result.raw_result
        self.output_parameters["cr_amplitude"].value = result["cr_amplitude"]
        self.output_parameters["cr_phase"].value = result["cr_phase"]
        self.output_parameters["cancel_amplitude"].value = result["cancel_amplitude"]
        self.output_parameters["cancel_phase"].value = result["cancel_phase"]
        self.output_parameters["cancel_beta"].value = result["cancel_beta"]
        self.output_parameters["rotary_amplitude"].value = result["rotary_amplitude"]
        self.output_parameters["zx_rotation_rate"].value = result["zx_rotation_rate"]

        output_parameters = self.attach_execution_id(execution_id)
        fig = self._plot_coeffs_history(result["coeffs_history"], label=label)
        figures: list = [fig]
        raw_data: list = []
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = session.get_session()
        label = "-".join(
            [exp.get_qubit_label(int(q)) for q in qid.split("-")]
        )  # e.g., "0-1" → "Q00-Q01"
        control, target = (
            exp.get_qubit_label(int(q)) for q in qid.split("-")
        )  # e.g., "0-1" → "Q00","Q01"

        raw_result = exp.obtain_cr_params(
            control,
            target,
        )
        fit_result = exp.calib_note.get_cr_param(label)
        if fit_result is None:
            error_message = "Fit result is None."
            raise ValueError(error_message)
        result = {
            "cr_amplitude": fit_result["cr_amplitude"],
            "cr_phase": fit_result["cr_phase"],
            "cancel_amplitude": fit_result["cancel_amplitude"],
            "cancel_phase": fit_result["cancel_phase"],
            "cancel_beta": fit_result["cancel_beta"],
            "rotary_amplitude": fit_result["rotary_amplitude"],
            "zx_rotation_rate": fit_result["zx_rotation_rate"],
            "coeffs_history": raw_result["coeffs_history"],
        }
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
