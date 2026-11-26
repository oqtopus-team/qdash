"""Schemas for re-running spectroscopy analysis on stored task results.

These endpoints let the chip page re-execute the resonator/qubit frequency
estimators on an already-saved spectroscopy figure with new parameters,
without re-running the experiment on hardware.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Largest inline figure accepted, as serialized JSON. Stored spectroscopy figures are a few MB.
MAX_INLINE_FIGURE_BYTES = 20 * 1024 * 1024


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
    resonator_assignment_order: list[Annotated[int, Field(ge=0, le=3)]] | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        json_schema_extra={"uniqueItems": True},
        description=(
            "Qubit offsets in increasing resonator-frequency order. "
            "Must contain each offset from 0 to 3 exactly once."
        ),
    )

    @field_validator("resonator_assignment_order")
    @classmethod
    def validate_resonator_assignment_order(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if len(value) != 4 or set(value) != set(range(4)):
            raise ValueError(
                "resonator_assignment_order must contain each qubit offset 0..3 exactly once"
            )
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
            "Task result to re-analyze. If omitted (and no figure is given), the latest "
            "matching task result for the (chip_id, qid) is used. Cannot be combined with "
            "figure."
        ),
    )
    figure: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Plotly figure JSON of a raw spectroscopy measurement to re-analyze instead of a "
            "stored task result. The first trace must have type 'heatmap' with plain lists of "
            "finite numbers: x (frequency, GHz) and y (power, dB) of at least 2 values each, "
            "and z with one row per y and one value per x. A figure labeled as marked is "
            "rejected. Only that heatmap, a named colorscale, and plain-text titles and sizes "
            "are kept; other traces and layout content (images, templates, shapes, "
            "annotations) are dropped. Stored run parameters do not apply, so unset "
            "parameters use the analysis defaults. At most 20 MiB as JSON. Cannot be combined "
            "with source_task_id."
        ),
    )
    include_image: bool = Field(
        default=False,
        description=(
            "If true, also render the marked figure as a PNG and return it base64-encoded "
            "in image_base64. Rendering adds latency, so the chip page leaves it off."
        ),
    )

    @field_validator("figure")
    @classmethod
    def validate_figure(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        size = len(json.dumps(value, separators=(",", ":")).encode("utf-8"))
        if size > MAX_INLINE_FIGURE_BYTES:
            raise ValueError(
                f"figure is {size} bytes as JSON; at most {MAX_INLINE_FIGURE_BYTES} are accepted"
            )
        data = value.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("figure must have a non-empty 'data' list of traces")
        first = data[0]
        if not isinstance(first, dict) or first.get("z") is None:
            raise ValueError("figure's first trace must be a heatmap with 'x', 'y', and 'z'")
        return value

    @model_validator(mode="after")
    def validate_single_source(self) -> ReanalyzeRequest:
        if self.figure is not None and self.source_task_id:
            raise ValueError("give either source_task_id or figure, not both")
        return self


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

    source_task_id: str | None = Field(
        default=None,
        description=(
            "Task result whose data was re-analyzed; null when an inline figure was re-analyzed."
        ),
    )
    source_task_name: str = Field(
        ...,
        description=(
            "Task whose analysis ran: the stored result's task name, or the endpoint's task "
            "for an inline figure."
        ),
    )
    qid: str
    figure: dict[str, Any] = Field(
        ...,
        description="Plotly figure JSON of the re-analyzed result with markers.",
    )
    output_parameters: list[ReanalyzeOutputParameter]
    image_base64: str | None = Field(
        default=None,
        description=(
            "Base64-encoded PNG of the marked figure. Set only when include_image was true "
            "and the server could render the figure."
        ),
    )
    image_media_type: str | None = Field(
        default=None,
        description="Media type of image_base64 (image/png), or null when no image is returned.",
    )
    image_error: str | None = Field(
        default=None,
        description=(
            "A fixed message saying the requested image could not be rendered; the cause is "
            "logged on the server only. Null when no image was requested or rendering "
            "succeeded."
        ),
    )
    committed: bool = Field(
        default=False,
        description="Always false in this version; persisting changes will land later.",
    )
