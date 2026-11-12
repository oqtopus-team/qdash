"""Plugin interfaces and implementations for 1-Qubit Scheduler.

This module provides a pluggable architecture for 1-qubit calibration scheduling,
allowing users to customize the ordering of qubits within MUX groups.

Architecture:
    - MuxOrderingStrategy: Base class for MUX-internal qubit ordering strategies
    - OrderingContext: Context object passed to ordering strategies

Example:
    ```python
    from qdash.workflow.engine.scheduler import OneQubitScheduler
    from qdash.workflow.engine.scheduler.one_qubit_plugins import (
        CheckerboardOrderingStrategy,
    )

    scheduler = OneQubitScheduler(chip_id="64Qv3")

    # Use checkerboard ordering for frequency isolation
    ordering = CheckerboardOrderingStrategy()
    schedule = scheduler.generate_from_mux(
        mux_ids=[0, 1, 2, 3],
        ordering_strategy=ordering,
    )
    ```
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from qdash.common.mux_mapping import MuxMapping

logger = logging.getLogger(__name__)


@dataclass
class OrderingContext:
    """Context object passed to MUX ordering strategies.

    Attributes:
        chip_id: Chip identifier (e.g., "64Qv3")
        grid_size: Grid dimension (8 for 64-qubit, 12 for 144-qubit)
        mux_grid_size: MUX grid dimension (4 for 64-qubit, 6 for 144-qubit)
        qid_to_mux: Mapping from qubit ID to MUX ID
        mux_mapping: MUX membership with local slots from the chip topology.
            If None, the legacy convention applies (MUX N = qubits 4N..4N+3).
    """

    chip_id: str
    grid_size: int
    mux_grid_size: int
    qid_to_mux: dict[str, int] = field(default_factory=dict)
    mux_mapping: MuxMapping | None = None

    def slot_members(self, mux_id: int) -> dict[int, str]:
        """Local slot -> qubit ID for ``mux_id``."""
        mapping = self.mux_mapping if self.mux_mapping is not None else MuxMapping.legacy()
        return mapping.slots_of(mux_id)


def _ordered_slots(slots: dict[int, str], preferred: list[int]) -> list[int]:
    """``preferred`` slots first, then any further slots of a larger MUX."""
    return [slot for slot in preferred if slot in slots] + sorted(
        slot for slot in slots if slot not in preferred
    )


class MuxOrderingStrategy(ABC):
    """Base class for MUX-internal qubit ordering strategies.

    Ordering strategies determine the execution order of qubits within
    each MUX group for parallel execution.
    """

    @abstractmethod
    def order_qids_in_mux(
        self,
        mux_id: int,
        qids: list[str],
        context: OrderingContext,
    ) -> list[str]:
        """Order qubits within a single MUX.

        Args:
            mux_id: MUX identifier
            qids: List of qubit IDs in this MUX (subset of its members)
            context: Context object containing chip configuration

        Returns:
            Ordered list of qubit IDs for sequential execution within this MUX
        """

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata.

        Returns:
            Dictionary containing strategy-specific metadata
        """

    @abstractmethod
    def generate_synchronized_steps(
        self,
        mux_ids: list[int],
        qids: list[str],
        context: OrderingContext,
    ) -> list[list[str]]:
        """Generate synchronized parallel steps across all MUXes.

        Args:
            mux_ids: List of MUX IDs to include
            qids: List of all qubit IDs
            context: Context object containing chip configuration

        Returns:
            List of steps, where each step is a list of qubit IDs
            that can be executed simultaneously
        """

    def __repr__(self) -> str:
        """String representation of the strategy."""
        return f"{self.__class__.__name__}()"


# ============================================================================
# Concrete Ordering Strategy Implementations
# ============================================================================


class DefaultOrderingStrategy(MuxOrderingStrategy):
    """Default ordering strategy - qubits in local slot order [0, 1, 2, 3].

    This is the simplest strategy that keeps the MUX's slot order. With the
    legacy mapping this is the natural qubit ID order.

    Example:
        ```python
        strategy = DefaultOrderingStrategy()
        # MUX 0: [0, 1, 2, 3] -> [0, 1, 2, 3]
        # MUX 1: [4, 5, 6, 7] -> [4, 5, 6, 7]
        ```
    """

    def order_qids_in_mux(
        self,
        mux_id: int,
        qids: list[str],
        context: OrderingContext,
    ) -> list[str]:
        """Return qubits in local slot order."""
        slot_of = {qid: slot for slot, qid in context.slot_members(mux_id).items()}
        return sorted(qids, key=lambda qid: (slot_of.get(qid, len(slot_of)), int(qid)))

    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata."""
        return {
            "strategy_name": "default",
            "description": "Natural qubit ID order",
        }

    def generate_synchronized_steps(
        self,
        mux_ids: list[int],
        qids: list[str],
        context: OrderingContext,
    ) -> list[list[str]]:
        """Generate synchronized steps in local slot order.

        Args:
            mux_ids: List of MUX IDs to include
            qids: List of all qubit IDs
            context: Context object

        Returns:
            One step per local slot (4 for 2x2 MUXes)
        """
        qid_set = set(qids)
        steps: dict[int, list[str]] = {}

        for mux_id in sorted(mux_ids):
            for slot, target_qid in sorted(context.slot_members(mux_id).items()):
                if target_qid in qid_set:
                    steps.setdefault(slot, []).append(target_qid)

        return [steps[slot] for slot in sorted(steps)]

    def __repr__(self) -> str:
        """String representation."""
        return "DefaultOrderingStrategy()"


class CheckerboardOrderingStrategy(MuxOrderingStrategy):
    """Checkerboard ordering strategy for frequency isolation.

    This strategy orders qubits within each MUX such that when all MUXes
    execute in parallel, adjacent qubits (which have similar frequencies)
    are never calibrated simultaneously.

    MUX internal layout (2x2, by local slot):
        slot0 slot1
        slot2 slot3

    Ordering pattern (slots come from the chip topology's MUX mapping):
        - Even MUX (mux_id % 2 == 0): [0, 1, 2, 3] slot order
        - Odd MUX (mux_id % 2 == 1): [2, 3, 0, 1] slot order

    This creates a chip-wide checkerboard pattern where each step
    calibrates qubits that are spatially and frequency-separated.

    Example:
        ```python
        strategy = CheckerboardOrderingStrategy()

        # MUX 0 (even): offsets [0, 1, 2, 3] -> qids [0, 1, 2, 3]
        # MUX 1 (odd):  offsets [2, 3, 0, 1] -> qids [6, 7, 4, 5]
        # MUX 2 (even): offsets [0, 1, 2, 3] -> qids [8, 9, 10, 11]
        # MUX 3 (odd):  offsets [2, 3, 0, 1] -> qids [14, 15, 12, 13]

        # Step 1: qids 0, 6, 8, 14, ... (checkerboard pattern)
        # Step 2: qids 1, 7, 9, 15, ...
        # Step 3: qids 2, 4, 10, 12, ...
        # Step 4: qids 3, 5, 11, 13, ...
        ```
    """

    # Offset order for even MUXes: [0, 1, 2, 3]
    EVEN_MUX_ORDER = [0, 1, 2, 3]
    # Offset order for odd MUXes: [2, 3, 0, 1]
    ODD_MUX_ORDER = [2, 3, 0, 1]

    def order_qids_in_mux(
        self,
        mux_id: int,
        qids: list[str],
        context: OrderingContext,
    ) -> list[str]:
        """Order qubits for checkerboard pattern."""
        # Determine which slot order to use
        offset_order = self.EVEN_MUX_ORDER if mux_id % 2 == 0 else self.ODD_MUX_ORDER

        slots = context.slot_members(mux_id)
        qid_set = set(qids)
        return [
            slots[slot] for slot in _ordered_slots(slots, offset_order) if slots[slot] in qid_set
        ]

    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata."""
        return {
            "strategy_name": "checkerboard",
            "description": "Frequency-aware checkerboard ordering",
            "even_mux_order": self.EVEN_MUX_ORDER,
            "odd_mux_order": self.ODD_MUX_ORDER,
        }

    def __repr__(self) -> str:
        """String representation."""
        return "CheckerboardOrderingStrategy()"

    def generate_synchronized_steps(
        self,
        mux_ids: list[int],
        qids: list[str],
        context: OrderingContext,
    ) -> list[list[str]]:
        """Generate synchronized parallel steps across all MUXes.

        Instead of ordering qubits within each MUX for sequential execution,
        this method generates 4 steps where each step contains qubits from
        all participating MUXes that can be executed simultaneously.

        Args:
            mux_ids: List of MUX IDs to include
            qids: List of all qubit IDs (subset to be scheduled)
            context: Context object containing chip configuration

        Returns:
            List of 4 steps, where each step contains qubit IDs to execute
            simultaneously across all MUXes in a checkerboard pattern.

        Example:
            For MUXes [0, 1, 2, 3]:
            - Step 0: [0, 6, 8, 14]  (checkerboard: non-adjacent)
            - Step 1: [1, 7, 9, 15]
            - Step 2: [2, 4, 10, 12]
            - Step 3: [3, 5, 11, 13]
        """
        qid_set = set(qids)
        steps: dict[int, list[str]] = {}

        for mux_id in sorted(mux_ids):
            slots = context.slot_members(mux_id)

            # Determine slot order for this MUX
            offset_order = self.EVEN_MUX_ORDER if mux_id % 2 == 0 else self.ODD_MUX_ORDER

            # The step is the slot's position in the parity order, so a MUX that lacks a
            # slot leaves that step empty instead of shifting its later slots forward.
            # Slots beyond the 2x2 order of a larger MUX follow in slot order.
            for slot in _ordered_slots(slots, offset_order):
                target_qid = slots[slot]
                if target_qid in qid_set:
                    step_idx = offset_order.index(slot) if slot in offset_order else slot
                    steps.setdefault(step_idx, []).append(target_qid)

        # Empty steps are never created
        return [steps[step_idx] for step_idx in sorted(steps)]


class DefaultSynchronizedStrategy(DefaultOrderingStrategy):
    """Synchronized strategy using natural qubit order.

    Inherits ordering and synchronized step generation from DefaultOrderingStrategy.
    Exists as a named strategy for use when only synchronized execution is needed.

    Example:
        For MUXes [0, 1]:
        - Step 0: [0, 4]  (offset 0 from each MUX)
        - Step 1: [1, 5]  (offset 1 from each MUX)
        - Step 2: [2, 6]  (offset 2 from each MUX)
        - Step 3: [3, 7]  (offset 3 from each MUX)
    """

    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata."""
        return {
            "strategy_name": "default_synchronized",
            "description": "Natural order synchronized steps",
        }

    def __repr__(self) -> str:
        """String representation."""
        return "DefaultSynchronizedStrategy()"
