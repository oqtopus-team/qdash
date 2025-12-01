"""Schema definitions for chip router."""

from typing import Any

from pydantic import BaseModel, ConfigDict
from qdash.datamodel.task import OutputParameterModel


class ExecutionResponseSummary(BaseModel):
    """ExecutionResponseSummaryV2 is a Pydantic model that represents the summary of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time of the execution.
        end_at (str): The end time of the execution.
        elapsed_time (str): The total elapsed time of the execution.

    """

    name: str
    execution_id: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str
    tags: list[str]
    note: dict


class Task(BaseModel):
    """Task is a Pydantic model that represents a task."""

    task_id: str | None = None
    qid: str | None = None
    name: str = ""  # Default empty string for name
    upstream_id: str | None = None
    status: str = "pending"  # Default status
    message: str | None = None
    input_parameters: dict[str, Any] | None = None
    output_parameters: dict[str, Any] | None = None
    output_parameter_names: list[str] | None = None
    note: dict[str, Any] | None = None
    figure_path: list[str] | None = None
    json_figure_path: list[str] | None = None
    raw_data_path: list[str] | None = None
    start_at: str | None = None
    end_at: str | None = None
    elapsed_time: str | None = None
    task_type: str | None = None
    default_view: bool = True
    over_threshold: bool = False


class ExecutionResponseDetail(BaseModel):
    """ExecutionResponseDetailV2 is a Pydantic model that represents the detail of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time

    """

    name: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str
    task: list[Task]
    note: dict


class ChipResponse(BaseModel):
    """Chip is a Pydantic model that represents a chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip.
        name (str): The name of the chip.

    """

    chip_id: str
    size: int = 64
    qubits: dict[str, Any] = {}
    couplings: dict[str, Any] = {}
    installed_at: str = ""


class CreateChipRequest(BaseModel):
    """Request model for creating a new chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip to create.
        size (int): The size of the chip (64, 144, 256, or 1024).

    """

    chip_id: str
    size: int = 64


class ChipDatesResponse(BaseModel):
    """Response model for chip dates."""

    data: list[str]


class MuxDetailResponse(BaseModel):
    """MuxDetailResponse is a Pydantic model that represents the response for fetching the multiplexer details."""

    mux_id: int
    detail: dict[str, dict[str, Task]]


class ListMuxResponse(BaseModel):
    """ListMuxResponse is a Pydantic model that represents the response for fetching the multiplexers."""

    muxes: dict[int, MuxDetailResponse]


class LatestTaskGroupedByChipResponse(BaseModel):
    """ChipTaskResponse is a Pydantic model that represents the response for fetching the tasks of a chip."""

    task_name: str
    result: dict[str, Task]


class TaskHistoryResponse(BaseModel):
    """TaskHistoryResponse is a Pydantic model that represents the response for fetching task history."""

    name: str
    data: dict[str, Task]


class TimeSeriesProjection(BaseModel):
    """TimeSeriesProjection is a Pydantic model that represents the projection for time series data."""

    qid: str
    output_parameters: dict[str, Any]
    start_at: str


class TimeSeriesData(BaseModel):
    """TimeSeriesData is a Pydantic model that represents the time series data."""

    data: dict[str, list[OutputParameterModel]] = {}

    model_config = ConfigDict(arbitrary_types_allowed=True)
