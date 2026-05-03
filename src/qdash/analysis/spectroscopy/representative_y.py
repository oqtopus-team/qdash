"""Representative-y strategy for qubit-spectroscopy peak analysis.

Walks the connected pixels of a labelled mountain and reports the y-row at
which the mountain first acquires a non-trivial frequency width. That row is
treated as the "representative" power level for the peak (used as
``f01_repr_db`` in the qubit-frequency estimator).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from collections.abc import Iterator

_NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = (
    (0, 1),  # up
    (-1, 0),  # left
    (1, 0),  # right
)


def walk_connected_pixels(
    mask: npt.NDArray[np.bool_],
    tip_x: int,
    tip_y: int,
) -> Iterator[tuple[int, int]]:
    """Yield (x, y) for every pixel reachable from the tip via 4-connectivity (up/left/right)."""
    height, width = mask.shape

    if not (0 <= tip_x < width and 0 <= tip_y < height):
        raise ValueError(f"({tip_x=}, {tip_y=}) is out of bounds")

    if not mask[tip_y, tip_x]:
        raise ValueError(f"({tip_x=}, {tip_y=}) is not on the mask")

    visited = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque([(tip_x, tip_y)])
    visited[tip_y, tip_x] = True

    while queue:
        x, y = queue.popleft()
        yield x, y

        for dx, dy in _NEIGHBOR_OFFSETS:
            nx = x + dx
            ny = y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if visited[ny, nx]:
                continue
            if not mask[ny, nx]:
                continue
            visited[ny, nx] = True
            queue.append((nx, ny))


class WidthEstimator(ABC):
    """Abstract base class for measuring the local width of a mask region."""

    @abstractmethod
    def estimate(self, mask: npt.NDArray[np.bool_], x: int, y: int) -> int:
        """Return the local width (in pixels) at (x, y)."""


@dataclass
class HorizontalRunLengthEstimator(WidthEstimator):
    """Width estimator based on the horizontal run length through (x, y)."""

    _width_cache_by_row: dict[int, npt.NDArray[np.int_]] = field(default_factory=dict, init=False)

    def estimate(self, mask: npt.NDArray[np.bool_], x: int, y: int) -> int:
        if not mask[y, x]:
            return 0

        row_cache = self._width_cache_by_row.get(y)
        if row_cache is None:
            row_cache = np.full(mask.shape[1], -1, dtype=np.int_)
            self._width_cache_by_row[y] = row_cache

        cached_width = row_cache[x]
        if cached_width >= 0:
            return int(cached_width)

        left = x
        while left - 1 >= 0 and mask[y, left - 1]:
            left -= 1

        right = x
        row_width = mask.shape[1]
        while right + 1 < row_width and mask[y, right + 1]:
            right += 1

        run_width = right - left + 1
        row_cache[left : right + 1] = run_width
        return int(run_width)


class PeakRepresentativeYStrategy(ABC):
    """Abstract base class for picking a representative y-row of a peak."""

    @abstractmethod
    def compute_representative_y(self, mask: npt.NDArray[np.bool_], tip_x: int, tip_y: int) -> int:
        """Return the y index that represents the peak."""


@dataclass(frozen=True)
class FirstPointMeetingWidthFromTipStrategy(PeakRepresentativeYStrategy):
    """Walks from the tip downward and returns the first row whose width meets ``min_width``."""

    width_estimator: WidthEstimator
    min_width: int = 2

    def compute_representative_y(self, mask: npt.NDArray[np.bool_], tip_x: int, tip_y: int) -> int:
        for x, y in walk_connected_pixels(mask=mask, tip_x=tip_x, tip_y=tip_y):
            if self.width_estimator.estimate(mask, x, y) >= self.min_width:
                return y
        return mask.shape[0]
