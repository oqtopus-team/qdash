"""Task execution result types.

These classes are used for communication between task preprocessing,
execution, and postprocessing phases.
"""

from typing import Any

import plotly.graph_objs as go
from pydantic import BaseModel, field_validator

from qdash.datamodel.task import (
    InputParameterModel,
    OutputParameterModel,
    ParameterModel,
    RunParameterModel,
)


class PreProcessResult(BaseModel):
    """Result class for task preprocessing.

    Attributes
    ----------
    input_parameters : dict[str, InputParameterModel]
        Calibration parameters loaded from backend (for provenance tracking).
    run_parameters : dict[str, RunParameterModel]
        Experiment configuration parameters (shots, ranges, etc.).
    """

    input_parameters: dict[str, InputParameterModel] = {}
    run_parameters: dict[str, RunParameterModel] = {}

    @field_validator("input_parameters", mode="before")
    @classmethod
    def convert_input_models(cls, values: Any) -> Any:
        """Accept persisted base models while normalizing to the input role."""
        if isinstance(values, dict):
            return {
                name: value.model_dump() if isinstance(value, ParameterModel) else value
                for name, value in values.items()
            }
        return values


class PostProcessResult(BaseModel):
    """Result class for task postprocessing.

    Attributes
    ----------
    validation_error : str | None
        If set, the task will be marked as failed **after** figures and output
        parameters have been saved.  This allows callers to reject a result
        (e.g. qubit frequency out of range) while still persisting the
        measurement artifacts for inspection.
    """

    model_config = {"arbitrary_types_allowed": True}

    output_parameters: dict[str, OutputParameterModel]
    figures: list[go.Figure | go.FigureWidget] = []
    raw_data: list[Any] = []
    validation_error: str | None = None

    @field_validator("output_parameters", mode="before")
    @classmethod
    def convert_output_models(cls, values: Any) -> Any:
        """Accept persisted base models while normalizing to the output role."""
        if isinstance(values, dict):
            return {
                name: value.model_dump() if isinstance(value, ParameterModel) else value
                for name, value in values.items()
            }
        return values


class RunResult(BaseModel):
    """Result class for task execution."""

    raw_result: Any
    r2: dict[str, float | None] | None = None

    def has_r2(self) -> bool:
        """Check if the result has R2 value."""
        return self.r2 is not None
