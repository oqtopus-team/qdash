from typing import ClassVar

import numpy as np
import plotly.graph_objs as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class ReadoutClassification(BaseTask):
    """Task to classify the readout."""

    name: str = "ReadoutClassification"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "average_readout_fidelity": OutputParameterModel(
            unit="a.u.",
            description="Average readout fidelity",
        ),
        "readout_fidelity_0": OutputParameterModel(
            unit="a.u.",
            description="Readout fidelity with preparation state 0",
        ),
        "readout_fidelity_1": OutputParameterModel(
            unit="a.u.",
            description="Readout fidelity with preparation state 1",
        ),
    }

    def plot_section_from_result(self, session: QubexSession, result, qid: str, bins=60):
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        clf = result["classifiers"][label]
        z0 = result["data"][label][label][0]
        z1 = result["data"][label][label][1]

        # 判別軸（c0→c1）と中点 m
        c0, c1 = clf.centers[0], clf.centers[1]
        u = (c1 - c0) / abs(c1 - c0)
        m = 0.5 * (c0 + c1)

        # 射影関数（断面）
        proj = lambda z: np.real((z - m) * np.conj(u))
        t0, t1 = proj(z0), proj(z1)
        mu0, mu1 = proj(np.array([c0]))[0], proj(np.array([c1]))[0]
        lo, hi = float(min(t0.min(), t1.min())), float(max(t0.max(), t1.max()))
        mid = 0.5 * (mu0 + mu1)

        # 1Dグリッド → IQへ戻して predict → ラベルが切り替わる点を境界とする
        t_grid = np.linspace(lo, hi, 2001)
        grid_points = m + t_grid * u  # complex
        preds = clf.predict(grid_points)

        # 変化点（しきい値候補）。複数あれば中点に最も近いものを採用
        change_idx = np.where(np.diff(preds) != 0)[0]
        thr = None
        if len(change_idx):
            candidates = t_grid[change_idx]
            thr = candidates[np.argmin(np.abs(candidates - mid))]

        fig = go.Figure()
        fig.add_histogram(x=t0, nbinsx=bins, name="|0⟩", opacity=0.6)
        fig.add_histogram(x=t1, nbinsx=bins, name="|1⟩", opacity=0.6)
        if thr is not None:
            fig.add_vline(x=thr, line_dash="dash", annotation_text="threshold")
        fig.update_layout(
            title=f"Cross-section : {label} (from predict)",
            barmode="overlay",
            xaxis_title="projection along c0→c1",
            yaxis_title="count",
            width=640,
            height=360,
        )
        return fig

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = run_result.raw_result
        self.output_parameters["average_readout_fidelity"].value = result["average_readout_fidelity"][label]
        self.output_parameters["readout_fidelity_0"].value = result["readout_fidelties"][label][0]
        self.output_parameters["readout_fidelity_1"].value = result["readout_fidelties"][label][1]
        output_parameters = self.attach_execution_id(execution_id)

        figures: list[go.Figure] = [self.plot_section_from_result(session, result, qid)]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = exp.build_classifier(targets=label)
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(f"Batch run is not implemented for {self.name} task. Use run method instead.")
