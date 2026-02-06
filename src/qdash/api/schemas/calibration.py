"""Schema definitions for calibration router."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CalibrationNoteResponse(BaseModel):
    """CalibrationNote is a subclass of BaseModel."""

    username: str
    execution_id: str
    task_id: str
    note: dict[str, Any]
    timestamp: datetime | None = None


class SeedImportSource(str, Enum):
    """Source of seed parameters."""

    QUBEX_PARAMS = "qubex_params"
    MANUAL = "manual"


class SeedImportRequest(BaseModel):
    """Request to import seed parameters from qubex or manual input.

    Attributes
    ----------
    chip_id : str
        Target chip ID (e.g., "64Qv3")
    source : SeedImportSource
        Source of the parameters
    parameters : list[str] | None
        List of parameter names to import. If None, imports all available.
    qids : list[str] | None
        List of qubit IDs to import. If None, imports all available.
    manual_data : dict[str, dict[str, Any]] | None
        Manual data when source is MANUAL.
        Format: {"parameter_name": {"Q0": value, "Q1": value, ...}}

    """

    chip_id: str = Field(..., description="Target chip ID")
    source: SeedImportSource = Field(
        SeedImportSource.QUBEX_PARAMS, description="Source of parameters"
    )
    parameters: list[str] | None = Field(
        None,
        description="Parameter names to import (None = all available)",
        examples=[["qubit_frequency", "readout_amplitude", "control_amplitude"]],
    )
    qids: list[str] | None = Field(
        None,
        description="Qubit IDs to import (None = all available)",
        examples=[["Q00", "Q01", "Q02"]],
    )
    manual_data: dict[str, dict[str, Any]] | None = Field(
        None,
        description="Manual data when source is MANUAL",
    )


class SeedImportResultItem(BaseModel):
    """Result for a single parameter import."""

    parameter_name: str
    qid: str
    value: float | int | str
    unit: str
    status: str = Field(..., description="'imported' or 'skipped' or 'error'")
    message: str | None = None


class SeedImportResponse(BaseModel):
    """Response from seed import operation."""

    chip_id: str
    source: str
    imported_count: int
    skipped_count: int
    error_count: int
    results: list[SeedImportResultItem]
    provenance_activity_id: str | None = Field(
        None, description="Activity ID for provenance tracking"
    )
