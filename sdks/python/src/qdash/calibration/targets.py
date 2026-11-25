"""The qubits or couplings a calibration starts from.

Each class serializes to the pipeline spec's ``targets`` object. The SDK sends that object;
the worker builds its runtime target from the same object, so a target means the same thing
on both sides.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["CalibrationTargets", "CouplingTargets", "MuxTargets", "QubitTargets"]


def _list(owner: str, name: str, value: Any) -> list[Any]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TypeError(f"{owner} {name} must be a list, got {value!r}")
    return list(value)


class CalibrationTargets(BaseModel):
    """Base of the target selections; serialize one with :meth:`to_spec`."""

    model_config = ConfigDict(extra="forbid")

    def to_spec(self) -> dict[str, Any]:
        """The targets as the pipeline spec's ``targets`` JSON object."""
        return self.model_dump(mode="json", exclude_defaults=True)


class QubitTargets(CalibrationTargets):
    """Explicit target qubits by the IDs QDash lists, e.g. ``QubitTargets(["0", "1"])``.

    Serializes to ``{"qids": [...]}``.
    """

    qids: list[str] = Field(min_length=1)

    def __init__(self, qids: Iterable[str] | None = None, /, **data: Any) -> None:
        if qids is not None:
            data["qids"] = _list("QubitTargets", "qids", qids)
        elif "qids" in data:
            data["qids"] = _list("QubitTargets", "qids", data["qids"])
        super().__init__(**data)

    @model_validator(mode="after")
    def _unique(self) -> QubitTargets:
        if len(set(self.qids)) != len(self.qids):
            raise ValueError("qids contains duplicates")
        return self


class MuxTargets(CalibrationTargets):
    """Every qubit of the given MUXes, e.g. ``MuxTargets([0, 1], exclude_qids=["5"])``.

    Serializes to ``{"mux_ids": [...], "exclude_qids": [...]}``; the MUXes resolve to qubits
    from the chip topology when the run starts.
    """

    mux_ids: list[int] = Field(min_length=1)
    exclude_qids: list[str] = Field(default_factory=list)

    def __init__(
        self,
        mux_ids: Iterable[int] | None = None,
        exclude_qids: Iterable[str] | None = None,
        /,
        **data: Any,
    ) -> None:
        if mux_ids is not None:
            data["mux_ids"] = mux_ids
        if exclude_qids is not None:
            data["exclude_qids"] = exclude_qids
        for name in ("mux_ids", "exclude_qids"):
            if name in data:
                data[name] = _list("MuxTargets", name, data[name])
        super().__init__(**data)

    @model_validator(mode="after")
    def _unique(self) -> MuxTargets:
        if len(set(self.mux_ids)) != len(self.mux_ids):
            raise ValueError("mux_ids contains duplicates")
        return self


class CouplingTargets(CalibrationTargets):
    """Directed coupling pairs, e.g. ``CouplingTargets([("0", "1"), ("4", "5")])``.

    Each pair is ``(control, target)`` and keeps its direction. Serializes to
    ``{"pairs": [[control, target], ...]}``.
    """

    pairs: list[tuple[str, str]] = Field(min_length=1)

    def __init__(self, pairs: Iterable[Iterable[str]] | None = None, /, **data: Any) -> None:
        if pairs is not None:
            data["pairs"] = pairs
        if "pairs" in data:
            data["pairs"] = [
                tuple(_list("CouplingTargets", "pair", pair))
                for pair in _list("CouplingTargets", "pairs", data["pairs"])
            ]
        super().__init__(**data)

    @model_validator(mode="after")
    def _distinct(self) -> CouplingTargets:
        for control, target in self.pairs:
            if control == target:
                raise ValueError(f"pair ({control!r}, {target!r}) couples a qubit with itself")
        if len(set(self.pairs)) != len(self.pairs):
            raise ValueError("pairs contains duplicates")
        return self
