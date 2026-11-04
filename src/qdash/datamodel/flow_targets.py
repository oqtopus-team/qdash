"""Validated, per-run overrides for user workflow calibration targets."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

TARGET_CONTEXT_KEY = "qdash_target_override"


class FlowTargetOverride(BaseModel):
    """Replace workflow targets for one execution; omission preserves source behavior."""

    model_config = ConfigDict(extra="forbid")

    mux_ids: list[Annotated[StrictInt, Field(ge=0)]] | None = None
    qids: list[Annotated[StrictStr, Field(pattern=r"^\d+$")]] | None = None
    exclude_qids: list[Annotated[StrictStr, Field(pattern=r"^\d+$")]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_targets(self) -> "FlowTargetOverride":
        if (self.mux_ids is None) == (self.qids is None):
            raise ValueError("Specify exactly one of mux_ids or qids")
        if not (self.mux_ids or self.qids):
            raise ValueError("Targets must not be empty")
        if self.qids is not None and self.exclude_qids:
            raise ValueError("exclude_qids requires mux_ids")
        for values in (self.mux_ids, self.qids, self.exclude_qids):
            if values is not None and len(values) != len(set(values)):
                raise ValueError("Target IDs must not contain duplicates")
        return self
