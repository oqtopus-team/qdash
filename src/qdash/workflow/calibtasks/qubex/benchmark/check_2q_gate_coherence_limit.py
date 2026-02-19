from typing import ClassVar

import numpy as np
import plotly.graph_objects as go
from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.analysis.util import calc_2q_gate_coherence_limit


class Check2QGateCoherenceLimit(QubexTask):
    """Task to calculate 2Q gate coherence limit from T1, T2, and gate duration."""

    name: str = "Check2QGateCoherenceLimit"
    task_type: str = "coupling"

    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "control_t1_average": ParameterModel(
            parameter_name="t1_average", qid_role="control", unit="μs"
        ),
        "control_t2_echo_average": ParameterModel(
            parameter_name="t2_echo_average", qid_role="control", unit="μs"
        ),
        "target_t1_average": ParameterModel(
            parameter_name="t1_average", qid_role="target", unit="μs"
        ),
        "target_t2_echo_average": ParameterModel(
            parameter_name="t2_echo_average", qid_role="target", unit="μs"
        ),
        "zx90_gate_time": ParameterModel(
            parameter_name="zx90_gate_time", qid_role="coupling", unit="ns"
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "two_qubit_gate_coherence_limit": ParameterModel(
            qid_role="coupling",
            unit="a.u.",
            description="2Q gate coherence limit fidelity",
        ),
    }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        gate_time = self._get_calibration_value("zx90_gate_time")
        if gate_time <= 0:
            raise ValueError(
                f"zx90_gate_time is {gate_time} for {qid}. Skipping coherence limit calculation."
            )

        control_t1_us = self._get_calibration_value("control_t1_average")
        control_t2_us = self._get_calibration_value("control_t2_echo_average")
        target_t1_us = self._get_calibration_value("target_t1_average")
        target_t2_us = self._get_calibration_value("target_t2_echo_average")

        # Convert μs to ns to match gate_time unit
        control_t1_ns = control_t1_us * 1000
        control_t2_ns = control_t2_us * 1000
        target_t1_ns = target_t1_us * 1000
        target_t2_ns = target_t2_us * 1000

        result = calc_2q_gate_coherence_limit(
            gate_time=gate_time,
            t1=(control_t1_ns, target_t1_ns),
            t2=(control_t2_ns, target_t2_ns),
        )
        return RunResult(
            raw_result={
                "fidelity": result["fidelity"],
                "gate_time": gate_time,
                "control_t1_ns": control_t1_ns,
                "control_t2_ns": control_t2_ns,
                "target_t1_ns": target_t1_ns,
                "target_t2_ns": target_t2_ns,
            }
        )

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        result = run_result.raw_result
        self.output_parameters["two_qubit_gate_coherence_limit"].value = result["fidelity"]
        output_parameters = self.attach_execution_id(execution_id)
        fig = self._make_gate_time_sweep_figure(
            gate_time=result["gate_time"],
            fidelity=result["fidelity"],
            control_t1_ns=result["control_t1_ns"],
            control_t2_ns=result["control_t2_ns"],
            target_t1_ns=result["target_t1_ns"],
            target_t2_ns=result["target_t2_ns"],
            qid=qid,
        )
        return PostProcessResult(output_parameters=output_parameters, figures=[fig])

    def _make_gate_time_sweep_figure(
        self,
        gate_time: float,
        fidelity: float,
        control_t1_ns: float,
        control_t2_ns: float,
        target_t1_ns: float,
        target_t2_ns: float,
        qid: str,
    ) -> go.Figure:
        """Create a gate time sweep figure showing coherence limit vs gate duration."""
        sweep_half_range = gate_time * 2
        gt_min = max(1, gate_time - sweep_half_range)
        gt_max = gate_time + sweep_half_range
        gate_times = np.linspace(gt_min, gt_max, 200)
        fidelities = [
            calc_2q_gate_coherence_limit(
                gate_time=gt,
                t1=(control_t1_ns, target_t1_ns),
                t2=(control_t2_ns, target_t2_ns),
            )["fidelity"]
            for gt in gate_times
        ]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=gate_times,
                y=fidelities,
                mode="lines",
                name="Coherence Limit",
                line={"color": "steelblue", "width": 2},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[gate_time],
                y=[fidelity],
                mode="markers",
                name=f"Current ({gate_time:.0f} ns)",
                marker={"color": "red", "size": 10, "symbol": "diamond"},
            )
        )
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

        ctrl, tgt = qid.split("-")
        fig.update_layout(
            title=(
                f"2Q Gate Coherence Limit - {qid}"
                f" (Ctrl T1={control_t1_ns / 1000:.1f} μs, T2={control_t2_ns / 1000:.1f} μs,"
                f" Tgt T1={target_t1_ns / 1000:.1f} μs, T2={target_t2_ns / 1000:.1f} μs)"
            ),
            xaxis_title="Gate Time (ns)",
            yaxis_title="Fidelity",
            showlegend=True,
            width=600,
            height=400,
        )
        return fig
