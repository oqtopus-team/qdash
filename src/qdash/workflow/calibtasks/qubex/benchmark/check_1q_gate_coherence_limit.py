from typing import ClassVar

import numpy as np
import plotly.graph_objects as go
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.analysis.util import calc_1q_gate_coherence_limit


class Check1QGateCoherenceLimit(QubexTask):
    """Task to calculate 1Q gate coherence limit from T1, T2, and gate duration."""

    name: str = "Check1QGateCoherenceLimit"
    task_type: str = "qubit"

    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "t1_average": None,  # Load from DB (μs)
        "t2_echo_average": None,  # Load from DB (μs)
    }

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "drag_hpi_duration": RunParameterModel(
            unit="ns",
            value_type="int",
            value=16,
            description="DRAG half-pi pulse duration",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "one_qubit_gate_coherence_limit": ParameterModel(
            unit="a.u.",
            description="1Q gate coherence limit fidelity",
        ),
    }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        gate_time = self.run_parameters["drag_hpi_duration"].get_value()
        t1_us = self._get_calibration_value("t1_average")
        t2_us = self._get_calibration_value("t2_echo_average")

        # Convert μs to ns to match gate_time unit
        t1_ns = t1_us * 1000
        t2_ns = t2_us * 1000

        result = calc_1q_gate_coherence_limit(
            gate_time=gate_time,
            t1=t1_ns,
            t2=t2_ns,
        )
        return RunResult(raw_result={
            "fidelity": result["fidelity"],
            "gate_time": gate_time,
            "t1_ns": t1_ns,
            "t2_ns": t2_ns,
        })

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        result = run_result.raw_result
        self.output_parameters["one_qubit_gate_coherence_limit"].value = result["fidelity"]
        output_parameters = self.attach_execution_id(execution_id)
        fig = self._make_gate_time_sweep_figure(
            gate_time=result["gate_time"],
            fidelity=result["fidelity"],
            t1_ns=result["t1_ns"],
            t2_ns=result["t2_ns"],
            qid=qid,
        )
        return PostProcessResult(output_parameters=output_parameters, figures=[fig])

    def _make_gate_time_sweep_figure(
        self,
        gate_time: float,
        fidelity: float,
        t1_ns: float,
        t2_ns: float,
        qid: str,
    ) -> go.Figure:
        """Create a gate time sweep figure showing coherence limit vs gate duration."""
        sweep_half_range = gate_time * 2
        gt_min = max(1, gate_time - sweep_half_range)
        gt_max = gate_time + sweep_half_range
        gate_times = np.linspace(gt_min, gt_max, 200)
        fidelities = [
            calc_1q_gate_coherence_limit(gate_time=gt, t1=t1_ns, t2=t2_ns)["fidelity"]
            for gt in gate_times
        ]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=gate_times,
            y=fidelities,
            mode="lines",
            name="Coherence Limit",
            line={"color": "steelblue", "width": 2},
        ))
        fig.add_trace(go.Scatter(
            x=[gate_time],
            y=[fidelity],
            mode="markers",
            name=f"Current ({gate_time:.0f} ns)",
            marker={"color": "red", "size": 10, "symbol": "diamond"},
        ))
        # Crosshair lines at current operating point
        fig.add_vline(
            x=gate_time,
            line_dash="dash",
            line_color="gray",
            line_width=1,
        )
        fig.add_hline(
            y=fidelity,
            line_dash="dash",
            line_color="gray",
            line_width=1,
            annotation_text=f"{fidelity:.6f}",
            annotation_position="top right",
        )

        fig.update_layout(
            title=f"1Q Gate Coherence Limit - {qid} (T1={t1_ns / 1000:.1f} μs, T2={t2_ns / 1000:.1f} μs)",
            xaxis_title="Gate Time (ns)",
            yaxis_title="Fidelity",
            showlegend=True,
            width=600,
            height=400,
        )
        return fig
