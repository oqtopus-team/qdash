from typing import Any, ClassVar

import numpy as np
import numpy.typing as npt
import plotly.graph_objs as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.datamodel.task import TaskTypes


class ReadoutClassification(QubexTask):
    """Task to classify the readout."""

    name: str = "ReadoutClassification"
    task_type = TaskTypes.QUBIT

    # High resolution for accurate threshold detection
    GRID_RESOLUTION: int = 2001
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

    def plot_section_from_result(
        self, backend: QubexBackend, result: dict[str, Any], qid: str, bins: int = 60
    ) -> go.Figure:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        clf = result["classifiers"][label]
        z0 = result["data"][label][label][0]
        z1 = result["data"][label][label][1]

        # Discrimination axis (c0→c1) and midpoint m
        c0, c1 = clf.centers[0], clf.centers[1]

        # Validate that classifier centers are different
        if abs(c1 - c0) == 0:
            raise ValueError("Classifier centers are identical, cannot compute discrimination axis")

        u = (c1 - c0) / abs(c1 - c0)
        m = 0.5 * (c0 + c1)

        # Projection function (cross-section)
        def proj(z: npt.NDArray[Any]) -> npt.NDArray[np.floating[Any]]:
            """Project complex data onto discrimination axis."""
            return np.real((z - m) * np.conj(u))

        t0, t1 = proj(z0), proj(z1)

        # Validate that data arrays are not empty
        if len(t0) == 0 or len(t1) == 0:
            raise ValueError("No data points available for visualization")
        mu0, mu1 = proj(np.array([c0]))[0], proj(np.array([c1]))[0]
        lo, hi = float(min(t0.min(), t1.min())), float(max(t0.max(), t1.max()))
        mid = 0.5 * (mu0 + mu1)

        # Grid points and threshold candidates: project back to IQ and predict, find label switching points
        t_grid = np.linspace(lo, hi, self.GRID_RESOLUTION)
        grid_points = m + t_grid * u  # complex
        preds = clf.predict(grid_points)

        # Find change points (threshold candidates). If multiple, choose the one closest to midpoint
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

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["average_readout_fidelity"].value = result[
            "average_readout_fidelity"
        ][label]
        self.output_parameters["readout_fidelity_0"].value = result["readout_fidelities"][label][0]
        self.output_parameters["readout_fidelity_1"].value = result["readout_fidelities"][label][1]
        output_parameters = self.attach_execution_id(execution_id)

        figures: list[go.Figure] = [self.plot_section_from_result(backend, result, qid)]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = exp.build_classifier(targets=label, save_dir=exp.classifier_dir)
        self.save_calibration(backend)
        return RunResult(raw_result=result)
