"""Task result parameters as stable SDK values, not the generated per-route models.

The API reports each input and output parameter of a task result as an object (``value``,
``unit``, ``error`` and metadata such as ``calibrated_at``), or, for older results, as a bare
value. :class:`Parameter` holds either form without inventing what the server left out, and
:class:`Parameters` maps parameter names to them. Nothing here sends a request.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas

# Columns of :meth:`Parameters.to_records`, in order, also when there are no parameters.
PARAMETER_COLUMNS: tuple[str, ...] = (
    "name",
    "value",
    "unit",
    "error",
    "value_type",
    "calibrated_at",
    "execution_id",
    "task_id",
    "description",
)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


@dataclass(frozen=True, repr=False)
class Parameter:
    """One parameter of a task result as the server reported it.

    ``value``, ``unit`` and ``error`` are None when the server left them out, as for an older
    result that reported a bare value. ``metadata`` holds every other field the server
    reported, as plain Python values (``calibrated_at``, ``execution_id``, ``task_id``,
    ``description``, ``source``, database comparison fields, ...), and nothing it did not; a
    ``unit`` or ``error`` of an unexpected type stays there under its own name instead of being
    dropped. ``raw`` is the reported item itself: the generated model, a bare value, or None.

    The fields cannot be reassigned and ``metadata`` is a read-only view, but neither is a
    deep copy: nested values such as a list ``value``, the ``source`` mapping, or a mapping
    ``raw`` are the objects as reported and stay mutable. Mutating them changes this parameter
    (and, for a mapping that was passed in, the caller's data); copy them before editing.
    """

    value: Any = None
    unit: str | None = None
    error: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    raw: Any = field(default=None, compare=False)

    @classmethod
    def from_reported(cls, reported: Any) -> Parameter:
        """A parameter from one reported item: a model, a mapping or a bare value."""
        fields = _reported_fields(reported)
        if fields is None:
            # An older result reported the value alone.
            return cls(value=reported, raw=reported)
        unit = fields.get("unit")
        error = fields.get("error")
        unit_ok = unit is None or isinstance(unit, str)
        error_ok = error is None or (isinstance(error, int | float) and not isinstance(error, bool))
        # A unit or error the typed fields cannot hold is kept in metadata, never dropped.
        typed = {"value"} | ({"unit"} if unit_ok else set()) | ({"error"} if error_ok else set())
        return cls(
            value=fields.get("value"),
            unit=unit if unit_ok else None,
            error=error if error_ok else None,
            metadata=MappingProxyType(
                {key: item for key, item in fields.items() if key not in typed}
            ),
            raw=reported,
        )

    @property
    def calibrated_at(self) -> dt.datetime | None:
        """When the value was calibrated, when reported; an ISO 8601 string is parsed."""
        value = self.metadata.get("calibrated_at")
        if isinstance(value, dt.datetime):
            return value
        if isinstance(value, str):
            try:
                return dt.datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @property
    def execution_id(self) -> str | None:
        """The execution that produced the value, when reported."""
        return _optional_str(self.metadata.get("execution_id"))

    @property
    def task_id(self) -> str | None:
        """The task result that produced the value, when reported."""
        return _optional_str(self.metadata.get("task_id"))

    @property
    def description(self) -> str | None:
        return _optional_str(self.metadata.get("description"))

    @property
    def value_type(self) -> str | None:
        return _optional_str(self.metadata.get("value_type"))

    def __repr__(self) -> str:
        return f"Parameter(value={self.value!r}, unit={self.unit!r}, error={self.error!r})"


def _reported_fields(reported: Any) -> dict[str, Any] | None:
    """The fields the server reported for a parameter object; None for a bare value."""
    if isinstance(reported, Mapping):
        return dict(reported)
    dump = getattr(reported, "model_dump", None)
    if dump is None:
        return None
    # Only the fields the server sent (extra fields included), never the model's defaults.
    fields: dict[str, Any] = dump(exclude_unset=True)
    return fields


class Parameters(Mapping[str, Parameter | None]):
    """Parameters of a task result by name, in the order the server reported them.

    A read-only mapping: names cannot be added, removed or replaced, though each
    :class:`Parameter` keeps the reported nested values as they are. A parameter the server listed as null stays None, so it is told apart
    from one reported with a null ``value``. :meth:`to_records` and :meth:`to_dataframe` turn
    it into a table.
    """

    def __init__(self, items: Mapping[str, Parameter | None] | None = None) -> None:
        self._items: dict[str, Parameter | None] = dict(items or {})

    @classmethod
    def from_reported(cls, reported: Mapping[str, Any] | None) -> Parameters:
        return cls(
            {
                name: None if item is None else Parameter.from_reported(item)
                for name, item in (reported or {}).items()
            }
        )

    def __getitem__(self, name: str) -> Parameter | None:
        return self._items[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"Parameters({self._items!r})"

    def to_records(self) -> list[dict[str, Any]]:
        """One row per parameter with the :data:`PARAMETER_COLUMNS`; a field the server did not
        report, and every field of a parameter listed as null, is None."""
        return [_record(name, parameter) for name, parameter in self._items.items()]

    def to_dataframe(self) -> pandas.DataFrame:
        """:meth:`to_records` as a pandas DataFrame, with the same columns when empty.

        Needs pandas, which the SDK does not install.
        """
        try:
            import pandas
        except ImportError:
            raise ImportError(
                "to_dataframe() needs pandas; install it with `pip install pandas`, or use "
                "to_records() instead"
            ) from None
        return pandas.DataFrame.from_records(self.to_records(), columns=list(PARAMETER_COLUMNS))


def _record(name: str, parameter: Parameter | None) -> dict[str, Any]:
    if parameter is None:
        return {column: (name if column == "name" else None) for column in PARAMETER_COLUMNS}
    return {
        "name": name,
        "value": parameter.value,
        "unit": parameter.unit,
        "error": parameter.error,
        "value_type": parameter.value_type,
        "calibrated_at": parameter.calibrated_at,
        "execution_id": parameter.execution_id,
        "task_id": parameter.task_id,
        "description": parameter.description,
    }


__all__ = ["PARAMETER_COLUMNS", "Parameter", "Parameters"]
