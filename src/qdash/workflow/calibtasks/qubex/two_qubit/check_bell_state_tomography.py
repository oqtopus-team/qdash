from typing import Any, ClassVar

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckBellStateTomography(QubexTask):
    """Task to check the bell state tomography."""

    name: str = "CheckBellStateTomography"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }

    # Input parameters from control and target qubits
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        # Control qubit parameters
        "control_qubit_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="qubit_frequency",
            qid_role="control",
            unit="GHz",
        ),
        "control_drag_hpi_amplitude": InputParameterSpec.required_database(
            parameter_name="drag_hpi_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "control_drag_hpi_length": InputParameterSpec.required_database(
            parameter_name="drag_hpi_length",
            qid_role="control",
            unit="ns",
        ),
        "control_drag_hpi_beta": InputParameterSpec.required_database(
            parameter_name="drag_hpi_beta",
            qid_role="control",
            unit="a.u.",
        ),
        "control_readout_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_frequency",
            qid_role="control",
            unit="GHz",
        ),
        "control_readout_amplitude": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "control_readout_length": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_length",
            qid_role="control",
            unit="ns",
        ),
        # Target qubit parameters
        "target_qubit_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="qubit_frequency",
            qid_role="target",
            unit="GHz",
        ),
        "target_readout_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_frequency",
            qid_role="target",
            unit="GHz",
        ),
        "target_readout_amplitude": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_amplitude",
            qid_role="target",
            unit="a.u.",
        ),
        "target_readout_length": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_length",
            qid_role="target",
            unit="ns",
        ),
        # CR parameters (from previous calibration)
        "cr_amplitude": InputParameterSpec.required_database(
            parameter_name="cr_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "cr_phase": InputParameterSpec.required_database(
            parameter_name="cr_phase",
            qid_role="control",
            unit="a.u.",
        ),
        "cancel_amplitude": InputParameterSpec.required_database(
            parameter_name="cancel_amplitude",
            qid_role="target",
            unit="a.u.",
        ),
        "cancel_phase": InputParameterSpec.required_database(
            parameter_name="cancel_phase",
            qid_role="target",
            unit="a.u.",
        ),
        "cancel_beta": InputParameterSpec.required_database(
            parameter_name="cancel_beta",
            qid_role="target",
            unit="a.u.",
        ),
        "rotary_amplitude": InputParameterSpec.required_database(
            parameter_name="rotary_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "zx_rotation_rate": InputParameterSpec.required_database(
            parameter_name="zx_rotation_rate",
            qid_role="coupling",
            unit="a.u.",
        ),
        "cr_ramptime": InputParameterSpec.required_database(
            parameter_name="cr_ramptime", qid_role="coupling", unit="ns"
        ),
        "zx90_gate_time": InputParameterSpec.required_database(
            parameter_name="zx90_gate_time", qid_role="coupling", unit="ns"
        ),
    }

    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "bell_state_fidelity": OutputParameterSpec(
            qid_role="coupling",
            unit="a.u.",
            description="Bell state fidelity",
            value_type="float",
        ),
    }

    def make_figure(self, result: dict[str, Any], label: str) -> go.Figure:
        """Create a figure from the result."""
        # Assuming result contains a 'figure' key with the figure data
        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Re", "Im"),
        )

        # Real part
        fig.add_trace(
            go.Heatmap(
                z=result["density_matrix"].real,
                zmin=-1,
                zmax=1,
                colorscale="RdBu_r",
            ),
            row=1,
            col=1,
        )

        # Imaginary part
        fig.add_trace(
            go.Heatmap(
                z=result["density_matrix"].imag,
                zmin=-1,
                zmax=1,
                colorscale="RdBu_r",
            ),
            row=1,
            col=2,
        )
        fig.update_layout(
            title=f"Bell state tomography: {label}",
            annotations=[
                {
                    "x": 0.5,
                    "y": 1.05,
                    "xref": "paper",
                    "yref": "paper",
                    "text": f"Fidelity: {result['fidelity']:.2f}",
                    "showarrow": False,
                }
            ],
            xaxis1={
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3],
                "ticktext": ["00", "01", "10", "11"],
                "scaleanchor": "y1",
                "tickangle": 0,
            },
            yaxis1={
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3],
                "ticktext": ["00", "01", "10", "11"],
                "scaleanchor": "x1",
                "autorange": "reversed",
            },
            xaxis2={
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3],
                "ticktext": ["00", "01", "10", "11"],
                "scaleanchor": "y2",
                "tickangle": 0,
            },
            yaxis2={
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3],
                "ticktext": ["00", "01", "10", "11"],
                "scaleanchor": "x2",
                "autorange": "reversed",
            },
            width=600,
            height=356,
            margin={"l": 70, "r": 70, "t": 90, "b": 70},
        )
        return fig

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        label = "-".join(
            [exp.get_qubit_label(int(q)) for q in qid.split("-")]
        )  # e.g., "0-1" → "Q00-Q01"
        result = run_result.raw_result
        self.output_parameters["bell_state_fidelity"].value = result["fidelity"]
        output_parameters = self.attach_execution_id(execution_id)
        result["figure"] = self.make_figure(result, label)
        figures: list[Any] = [result["figure"]]
        raw_data: list[Any] = []
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        control, target = (
            exp.get_qubit_label(int(q)) for q in qid.split("-")
        )  # e.g., "0-1" → "Q00","Q01"
        result = exp.bell_state_tomography(
            control,
            target,
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
