"""Schema definitions for chip router."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, field_serializer, field_validator
from qdash.common.datetime_utils import format_elapsed_time, parse_elapsed_time


class ChipResponse(BaseModel):
    """Chip is a Pydantic model that represents a chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip.
        size (int): The size of the chip.
        topology_id (str | None): Topology template ID.
        qubits (dict): Qubit information.
        couplings (dict): Coupling information.
        installed_at (str): Installation timestamp.

    """

    chip_id: str
    size: int = 64
    topology_id: str | None = None
    qubits: dict[str, Any] = {}
    couplings: dict[str, Any] = {}
    installed_at: datetime | None = None


class CreateChipRequest(BaseModel):
    """Request model for creating a new chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip to create.
        size (int): The size of the chip (64, 144, 256, or 1024).
        topology_id (str | None): Topology template ID. If not provided, defaults to 'square-lattice-mux-{size}'.

    """

    chip_id: str
    size: int = 64
    topology_id: str | None = None


class ChipDatesResponse(BaseModel):
    """Response model for chip dates."""

    data: list[str]


class MuxTask(BaseModel):
    """Task information for mux display."""

    task_id: str | None = None
    qid: str | None = None
    name: str = ""
    upstream_id: str | None = None
    status: str = "pending"
    message: str | None = None
    input_parameters: dict[str, Any] | None = None
    output_parameters: dict[str, Any] | None = None
    output_parameter_names: list[str] | None = None
    note: dict[str, Any] | None = None
    figure_path: list[str] | None = None
    json_figure_path: list[str] | None = None
    raw_data_path: list[str] | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    task_type: str | None = None

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> timedelta | None:
        """Parse elapsed_time from various formats."""
        return parse_elapsed_time(v)

    @field_serializer("elapsed_time")
    @classmethod
    def _serialize_elapsed_time(cls, v: timedelta | None) -> str | None:
        """Serialize elapsed_time to H:MM:SS format."""
        return format_elapsed_time(v) if v else None


class MuxDetailResponse(BaseModel):
    """MuxDetailResponse is a Pydantic model that represents the response for fetching the multiplexer details."""

    mux_id: int
    detail: dict[str, dict[str, MuxTask]]


class ListMuxResponse(BaseModel):
    """ListMuxResponse is a Pydantic model that represents the response for fetching the multiplexers."""

    muxes: dict[int, MuxDetailResponse]


class ListChipsResponse(BaseModel):
    """Response model for listing all chips.

    Wraps list of chips for API consistency and future extensibility (e.g., pagination).
    """

    chips: list[ChipResponse]
