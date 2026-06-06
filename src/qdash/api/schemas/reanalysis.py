"""Schemas for re-running spectroscopy analysis on stored task results.

These endpoints let the chip page re-execute the resonator/qubit frequency
estimators on an already-saved spectroscopy figure with new parameters,
without re-running the experiment on hardware.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ReanalyzeResonatorSpectroscopyParams(BaseModel):
    """Optional analysis-parameter overrides for resonator spectroscopy.

    Any field left ``None`` falls back to the default in
    :class:`EstimateResonatorFrequencyConfig`.
    """

    num_resonators: int | None = Field(
        default=None,
        description="Number of resonators to detect in the MUX (typically 4).",
    )
    high_power_min: float | None = Field(
        default=None, description="Minimum power (dB) for the high-power region."
    )
    high_power_max: float | None = Field(
        default=None, description="Maximum power (dB) for the high-power region."
    )
    low_power: float | None = Field(
        default=None, description="Power level (dB) sampled for low-power peaks."
    )
    bare_shift_estimator_type: Literal["config", "high_frequency_strength"] | None = Field(
        default=None,
        description=(
            "If 'high_frequency_strength', the high/low-power boundary is "
            "auto-detected from the FFT energy of each row, overriding "
            "high_power_min/max/low_power."
        ),
    )
    bare_shift_strength_limit: float | None = Field(
        default=None,
        description="Strength cutoff for the high_frequency_strength estimator.",
    )
    resonator_assignment_pattern: str | None = Field(
        default=None,
        description=(
            "Named resonator assignment pattern: default or 16q. "
            "Use 16q for mux[0], mux[3], mux[1], mux[2]."
        ),
    )

    @field_validator("resonator_assignment_pattern")
    @classmethod
    def validate_resonator_assignment_pattern(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in {"default", "16q"}:
            raise ValueError("resonator_assignment_pattern must be 'default' or '16q'")
        return value


class ReanalyzeQubitSpectroscopyParams(BaseModel):
    """Optional analysis-parameter overrides for qubit spectroscopy."""

    binarize_threshold_sigma_plus: float | None = Field(default=None)
    binarize_threshold_sigma_minus: float | None = Field(default=None)
    top_power: float | None = Field(default=None)
    f01_height_min: float | None = Field(default=None)
    f12_distance_min: float | None = Field(default=None)
    f12_distance_max: float | None = Field(default=None)
    f12_height_min: float | None = Field(default=None)
    retry_with_trim: bool | None = Field(
        default=None,
        description=(
            "If true, retry after trimming the highest-power row when no f01 is found. "
            "If f01 is still not found, trim one additional row and retry once more."
        ),
    )


class ReanalyzeRequest(BaseModel):
    """Common request envelope for both spectroscopy reanalyses."""

    source_task_id: str | None = Field(
        default=None,
        description=(
            "Task result to re-analyze. If omitted, the latest matching task "
            "result for the (chip_id, qid) is used."
        ),
    )


class ReanalyzeResonatorSpectroscopyRequest(ReanalyzeRequest):
    """Request body for re-running CheckResonatorSpectroscopy analysis."""

    parameters: ReanalyzeResonatorSpectroscopyParams = Field(
        default_factory=ReanalyzeResonatorSpectroscopyParams
    )


class ReanalyzeQubitSpectroscopyRequest(ReanalyzeRequest):
    """Request body for re-running CheckQubitSpectroscopy analysis."""

    parameters: ReanalyzeQubitSpectroscopyParams = Field(
        default_factory=ReanalyzeQubitSpectroscopyParams
    )


class ReanalyzeOutputParameter(BaseModel):
    """A single re-analyzed output value."""

    name: str
    value: float
    unit: str = ""


class ReanalyzeResponse(BaseModel):
    """Preview response from a reanalyze endpoint.

    ``figure`` carries a Plotly figure as a plain JSON dict so the UI can
    render it directly. The DB is *not* mutated by this endpoint; commit
    will be added in a follow-up.
    """

    source_task_id: str = Field(..., description="Task result whose data was re-analyzed.")
    source_task_name: str
    qid: str
    figure: dict[str, Any] = Field(
        ...,
        description="Plotly figure JSON of the re-analyzed result with markers.",
    )
    output_parameters: list[ReanalyzeOutputParameter]
    committed: bool = Field(
        default=False,
        description="Always false in this version; persisting changes will land later.",
    )
