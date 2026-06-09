from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

_T = TypeVar("_T")


@dataclass(slots=True)
class ApiResponse(Generic[_T]):
    """Typed REST response container."""

    status_code: int
    data: _T
    headers: dict[str, str]
