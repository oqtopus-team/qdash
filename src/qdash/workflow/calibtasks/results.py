"""Task execution result types.

These classes are used for communication between task preprocessing,
execution, and postprocessing phases.
"""

from typing import Any

import plotly.graph_objs as go
from pydantic import BaseModel
from qdash.datamodel.task import ParameterModel, RunParameterModel


class PreProcessResult(BaseModel):
    """Result class for task preprocessing.

    Attributes
    ----------
    input_parameters : dict[str, ParameterModel]
        Calibration parameters loaded from backend (for provenance tracking).
    run_parameters : dict[str, RunParameterModel]
        Experiment configuration parameters (shots, ranges, etc.).
    """

    input_parameters: dict[str, ParameterModel | None] = {}
    run_parameters: dict[str, RunParameterModel] = {}


class PostProcessResult(BaseModel):
    """Result class for task postprocessing."""

    model_config = {"arbitrary_types_allowed": True}

    output_parameters: dict[str, ParameterModel]
    figures: list[go.Figure | go.FigureWidget] = []
    raw_data: list[Any] = []


class RunResult(BaseModel):
    """Result class for task execution."""

    raw_result: Any
    r2: dict[str, float | None] | None = None

    def has_r2(self) -> bool:
        """Check if the result has R2 value."""
        return self.r2 is not None
