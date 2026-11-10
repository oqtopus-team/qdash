"""Validated, per-run overrides for user workflow calibration targets."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

TARGET_CONTEXT_KEY = "qdash_target_override"

TargetMode = Literal["mux_ids", "qids", "coupling_pairs"]

QubitId = Annotated[StrictStr, Field(pattern=r"^\d+$")]
# A directed ``[control, target]`` pair; ``["63", "85"]`` and ``["85", "63"]`` differ.
CouplingPair = Annotated[list[QubitId], Field(min_length=2, max_length=2)]


class FlowTargetOverride(BaseModel):
    """Replace workflow targets for one execution; omission preserves source behavior."""

    model_config = ConfigDict(extra="forbid")

    mux_ids: list[Annotated[StrictInt, Field(ge=0)]] | None = None
    qids: list[QubitId] | None = None
    coupling_pairs: list[CouplingPair] | None = Field(
        None,
        description=(
            "Directed [control, target] qubit pairs; parallel groups are scheduled automatically"
        ),
    )
    exclude_qids: list[QubitId] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_targets(self) -> "FlowTargetOverride":
        selected = [
            values
            for values in (self.mux_ids, self.qids, self.coupling_pairs)
            if values is not None
        ]
        if len(selected) != 1:
            raise ValueError("Specify exactly one of mux_ids, qids or coupling_pairs")
        if not selected[0]:
            raise ValueError("Targets must not be empty")
        if self.mux_ids is None and self.exclude_qids:
            raise ValueError("exclude_qids requires mux_ids")
        for values in (self.mux_ids, self.qids, self.exclude_qids):
            if values is not None and len(values) != len(set(values)):
                raise ValueError("Target IDs must not contain duplicates")
        if self.coupling_pairs is not None:
            pairs = [tuple(pair) for pair in self.coupling_pairs]
            if any(control == target for control, target in pairs):
                raise ValueError("A coupling pair needs two different qubits")
            if len(pairs) != len(set(pairs)):
                raise ValueError("Coupling pairs must not contain duplicates")
        return self

    @property
    def mode(self) -> TargetMode:
        """Return the selected target type."""
        if self.mux_ids is not None:
            return "mux_ids"
        if self.qids is not None:
            return "qids"
        return "coupling_pairs"

    def pairs(self) -> list[tuple[str, str]]:
        """Return the selected directed pairs as ``(control, target)`` tuples."""
        return [(control, target) for control, target in self.coupling_pairs or []]
