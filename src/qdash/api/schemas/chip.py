"""Schema definitions for chip router."""

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from qdash.common.utils.chip_id import validate_chip_id
from qdash.common.utils.datetime import format_elapsed_time, parse_elapsed_time
from qdash.datamodel.note import NoteModel
from qdash.datamodel.task import TaskResultInputParameter, TaskResultOutputParameter


class ChipResponse(BaseModel):
    """Chip response model.

    Qubit and coupling data are stored in separate collections for scalability
    and should be fetched via dedicated endpoints (/chips/{chip_id}/qubits, etc.).

    Attributes
    ----------
        chip_id (str): The ID of the chip.
        size (int): The size of the chip.
        topology_id (str | None): Topology template ID.
        qubit_count (int): Number of qubits in the chip.
        coupling_count (int): Number of couplings in the chip.
        installed_at (datetime | None): Installation timestamp.

    """

    chip_id: str
    size: int = 64
    topology_id: str | None = None
    qubit_count: int = 0
    coupling_count: int = 0
    installed_at: datetime | None = None
    activity_status: Literal["active", "inactive"] = "active"
    current_cooldown_id: str | None = None
    note: NoteModel = Field(default_factory=NoteModel)


class ChipConfigOptions(BaseModel):
    """How to create ``<chip_id>/`` in the Qubex configuration tree (system_id == chip_id)."""

    create: bool = Field(
        default=True, description="Create the directory when it does not exist yet"
    )
    source_system_id: str | None = Field(
        default=None,
        description="Existing system whose wiring and hardware files are copied; empty wiring when omitted",
    )
    backend: Literal["quel1", "quel3"] | None = Field(
        default=None,
        description="Backend of the new system; taken from the source system when one is given",
    )
    preset: Literal["fake", "qibocal"] | None = Field(
        default=None,
        description=(
            "Create the chip from the deployment backend's preset instead of hardware files. "
            "'fake' writes the virtual device's configuration and is offered only on the fake "
            "backend; 'qibocal' creates the one-qubit emulator chip, writes no files, and is "
            "offered only on the qibocal backend. Each preset needs its own topology"
        ),
    )

    @model_validator(mode="after")
    def validate_preset(self) -> "ChipConfigOptions":
        if self.preset is not None and (
            not self.create or self.source_system_id is not None or self.backend is not None
        ):
            raise ValueError(
                "A configuration preset cannot be combined with create=false, "
                "source_system_id or backend"
            )
        return self


class CreateChipRequest(BaseModel):
    """Request model for creating a new chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip to create.
        size (int): The size of the chip (64, 144, 256, or 1024).
        topology_id (str | None): Topology template ID. If not provided, defaults to 'square-lattice-mux-{size}'.

    """

    chip_id: str = Field(
        description="Chip ID: starts with a letter or digit; contains only letters, digits, '.', '-' and '_'. Reserved names template, archive, schemas and scripts are not allowed."
    )
    size: int = 64
    topology_id: str | None = None
    config: ChipConfigOptions | None = Field(
        default=None,
        description="Qubex configuration directory to create; defaults to creating one",
    )

    @field_validator("chip_id")
    @classmethod
    def validate_directory_name(cls, value: str) -> str:
        return validate_chip_id(value)


class ChipConfigResult(BaseModel):
    """Outcome of creating the chip's configuration directory."""

    status: Literal["created", "existing", "skipped"]
    path: str
    source_system_id: str | None = None
    backend: str | None = None
    preset: str | None = None
    files: list[str] = Field(default_factory=list)
    message: str = ""


class CreateChipResponse(ChipResponse):
    """A created chip plus what happened to its configuration directory."""

    config: ChipConfigResult | None = None


class ConfigSourceResponse(BaseModel):
    """An existing system whose wiring a new chip can copy."""

    system_id: str
    backend: str
    mux_count: int
    files: list[str]


class ConfigPresetResponse(BaseModel):
    """A complete configuration a new chip can start from."""

    preset_id: str
    name: str
    description: str
    topology_id: str = Field(description="Topology the chip must use with this preset")
    n_qubits: int
    mux_count: int
    workflow_template_id: str = Field(
        description="Flow template that brings up and calibrates a chip created from the preset"
    )
    requires_config_tree: bool = Field(
        default=True,
        description=(
            "Whether the preset writes files into the Qubex configuration tree, so a chip can "
            "be created only while one is mounted"
        ),
    )


class ListConfigSourcesResponse(BaseModel):
    """Systems available as wiring sources for a new chip."""

    available: bool = Field(description="Whether a Qubex configuration tree is mounted")
    sources: list[ConfigSourceResponse]
    deployment_backend: str | None = Field(
        default=None,
        description=(
            "Backend this deployment calibrates with (DEFAULT_BACKEND), e.g. qubex, fake or qibocal"
        ),
    )
    presets: list[ConfigPresetResponse] = Field(
        default_factory=list,
        description=(
            "Presets of the deployment backend, listed even when no tree is mounted; "
            "the fake preset only on the fake backend and the qibocal preset only on the "
            "qibocal backend"
        ),
    )


class UpdateChipRequest(BaseModel):
    """Body for updating chip metadata. All fields optional."""

    topology_id: str | None = None
    activity_status: Literal["active", "inactive"] | None = None
    note: str | None = Field(
        default=None,
        max_length=5000,
        description="Free-form note text (overwrites note.content)",
    )


class ChipDeletionImpactResponse(BaseModel):
    """Counts of related rows that would be affected by deleting this chip."""

    chip_id: str
    qubits: int = Field(..., description="QubitDocument rows that would be hard-deleted")
    couplings: int = Field(..., description="CouplingDocument rows that would be hard-deleted")
    task_results: int = Field(
        ..., description="task_result_history rows kept for audit (not deleted)"
    )
    qubit_history_snapshots: int = Field(
        ..., description="qubit_history rows kept for audit (not deleted)"
    )
    coupling_history_snapshots: int = Field(
        ..., description="coupling_history rows kept for audit (not deleted)"
    )
    cooldowns_referencing: int = Field(
        ..., description="Cool-downs that include this chip and would have it removed"
    )
    can_delete_safely: bool = Field(
        ...,
        description=(
            "True if no QubitDocument or CouplingDocument rows exist (DELETE without "
            "force succeeds). When false, force=true is required."
        ),
    )


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
    input_parameters: dict[str, TaskResultInputParameter] | None = None
    output_parameters: dict[str, TaskResultOutputParameter] | None = None
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
    """Response model for listing chips."""

    chips: list[ChipResponse]
    total: int


class QubitResponse(BaseModel):
    """Response model for a single qubit."""

    qid: str
    chip_id: str
    status: str = "pending"
    data: dict[str, Any] = {}
    note: NoteModel = Field(default_factory=NoteModel)
    metric_notes: dict[str, NoteModel] = Field(default_factory=dict)


class ListQubitsResponse(BaseModel):
    """Response model for listing qubits with pagination."""

    qubits: list[QubitResponse]
    total: int
    limit: int
    offset: int


class CouplingResponse(BaseModel):
    """Response model for a single coupling."""

    qid: str
    chip_id: str
    status: str = "pending"
    data: dict[str, Any] = {}
    note: NoteModel = Field(default_factory=NoteModel)
    metric_notes: dict[str, NoteModel] = Field(default_factory=dict)


class ListCouplingsResponse(BaseModel):
    """Response model for listing couplings with pagination."""

    couplings: list[CouplingResponse]
    total: int
    limit: int
    offset: int


class MetricHeatmapResponse(BaseModel):
    """Response model for metric heatmap data.

    Returns only the metric values keyed by qubit/coupling ID.
    Much smaller than full chip data (~5KB vs ~300KB for 64 qubits).
    """

    chip_id: str
    metric: str
    values: dict[str, float | None]
    unit: str | None = None


class MetricsSummaryResponse(BaseModel):
    """Response model for aggregated metrics summary.

    Returns statistical summary computed by the database.
    Minimal data transfer (~0.1KB).
    Metrics are loaded dynamically from metrics.yaml config.
    """

    chip_id: str
    qubit_count: int
    averages: dict[str, float | None] = {}  # Dynamic: {metric_key: avg_value}
