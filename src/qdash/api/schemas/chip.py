"""Schema definitions for chip router."""

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from qdash.common.utils.datetime import format_elapsed_time, parse_elapsed_time
from qdash.datamodel.note import NoteModel
from qdash.datamodel.task import TaskResultInputParameter, TaskResultOutputParameter


class ChipPublishStatus(BaseModel):
    """How the generated configuration files were published."""

    status: Literal["published", "recorded", "failed", "skipped"] = Field(
        description=(
            "published: committed and pushed; recorded: written locally and logged "
            "(no remote); failed: files and database records exist but the remote "
            "rejected them; skipped: nothing to publish"
        )
    )
    mode: str | None = Field(default=None, description="Repository mode (github, local-git, plain)")
    commit: str | None = None
    message: str | None = None


class ChipProvisioningResult(BaseModel):
    """Configuration files generated when a chip or System is created."""

    provisioned: bool = Field(description="False when only database records were created")
    layout: str = Field(description="Configuration tree layout: shared or legacy")
    system_ids: list[str] = Field(default_factory=list)
    inherited_from: str | None = Field(
        default=None, description="Chip whose wiring and backend were copied"
    )
    files: list[str] = Field(
        default_factory=list, description="Repository-relative paths written or updated"
    )
    publish: ChipPublishStatus = Field(default_factory=lambda: ChipPublishStatus(status="skipped"))
    warnings: list[str] = Field(default_factory=list)


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
    provisioning: ChipProvisioningResult | None = Field(
        default=None,
        description="Configuration files generated for the chip; only on creation",
    )


class CreateChipRequest(BaseModel):
    """Request model for creating a new chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip to create.
        size (int): The size of the chip (64, 144, 256, or 1024).
        topology_id (str | None): Topology template ID. If not provided, defaults to 'square-lattice-mux-{size}'.
        display_name (str | None): Name written to chip.yaml; defaults to the chip ID.
        provision_config (bool | None): Also generate the Qubex configuration files.
            None (default) generates them when the configuration tree uses the shared layout.
        backend (str | None): Backend of the generated System (quel1 or quel3).
            Defaults to the inherited chip's backend, else quel1.
        inherit_wiring_from (str | None): Chip whose wiring and Systems are copied.
            Defaults to the previous chip on the cool-down's cryostat.
        cooldown_id (str | None): Cool-down to load the chip into.

    """

    chip_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$", max_length=64)
    size: int = 64
    topology_id: str | None = None
    display_name: str | None = Field(default=None, max_length=200)
    provision_config: bool | None = None
    backend: str | None = Field(default=None, pattern=r"^[a-z0-9]+$")
    inherit_wiring_from: str | None = Field(default=None, max_length=64)
    cooldown_id: str | None = None


class ChipSystemInfo(BaseModel):
    """One Qubex System driving the chip."""

    system_id: str
    chip_id: str = Field(description="Chip ID as the Qubex configuration names it")
    driver: str = Field(description="QDash backend driver, e.g. qubex")
    backend: str = Field(description="Hardware kind inside the driver, e.g. quel1 or quel3")
    mux_ids: list[int] = Field(default_factory=list)
    box_ids: list[str] = Field(default_factory=list, description="Boxes its wiring references")
    is_default: bool = Field(description="Whether this System is named like the chip")
    has_params: bool = Field(description="params/<system_id>/ exists")
    has_calib_note: bool = Field(description="calibration/<system_id>/calib_note.json exists")
    settings: dict[str, Any] = Field(default_factory=dict, description="The system.yaml entry")


class ChipSystemsResponse(BaseModel):
    """Systems of a chip as read from the Qubex configuration."""

    chip_id: str
    layout: str = Field(description="Configuration tree layout: shared or legacy")
    provisionable: bool = Field(description="Whether Systems can be added (shared layout)")
    systems: list[ChipSystemInfo] = Field(default_factory=list)
    message: str | None = Field(
        default=None, description="Why no Systems could be read, when the list is empty"
    )


class AddChipSystemRequest(BaseModel):
    """Add a System driving some of the chip's MUXes with another backend."""

    backend: str = Field(pattern=r"^[a-z0-9]+$", description="quel1 or quel3")
    mux_ids: list[int] = Field(min_length=1, description="MUXes moved to the new System")
    settings: dict[str, Any] = Field(
        default_factory=dict, description="Backend section of the system.yaml entry"
    )
    wiring: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Wiring rows of the moved MUXes on the new hardware. When omitted the rows "
            "keep their current ports."
        ),
    )


class AddChipSystemResponse(BaseModel):
    """Result of adding a System."""

    system: ChipSystemInfo
    files: list[str] = Field(default_factory=list)
    publish: ChipPublishStatus
    warnings: list[str] = Field(default_factory=list)


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
