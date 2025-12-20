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

logger = logging.getLogger(__name__)


@dataclass
class OrderingContext:
    """Context object passed to MUX ordering strategies.

    Attributes:
        chip_id: Chip identifier (e.g., "64Qv3")
        grid_size: Grid dimension (8 for 64-qubit, 12 for 144-qubit)
        mux_grid_size: MUX grid dimension (4 for 64-qubit, 6 for 144-qubit)
        qid_to_mux: Mapping from qubit ID to MUX ID
    """

    chip_id: str
    grid_size: int
    mux_grid_size: int
    qid_to_mux: dict[str, int] = field(default_factory=dict)


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
            qids: List of qubit IDs in this MUX (subset of [4N, 4N+1, 4N+2, 4N+3])
            context: Context object containing chip configuration

        Returns:
            Ordered list of qubit IDs for sequential execution within this MUX
        """
        pass

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata.

        Returns:
            Dictionary containing strategy-specific metadata
        """
        pass

    def __repr__(self) -> str:
        """String representation of the strategy."""
        return f"{self.__class__.__name__}()"


# ============================================================================
# Concrete Ordering Strategy Implementations
# ============================================================================


class DefaultOrderingStrategy(MuxOrderingStrategy):
    """Default ordering strategy - qubits in natural order [0, 1, 2, 3].

    This is the simplest strategy that maintains the natural qubit ID order
    within each MUX.

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
        """Return qubits in natural order."""
        return sorted(qids, key=lambda x: int(x))

    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata."""
        return {
            "strategy_name": "default",
            "description": "Natural qubit ID order",
        }

    def __repr__(self) -> str:
        """String representation."""
        return "DefaultOrderingStrategy()"


class CheckerboardOrderingStrategy(MuxOrderingStrategy):
    """Checkerboard ordering strategy for frequency isolation.

    This strategy orders qubits within each MUX such that when all MUXes
    execute in parallel, adjacent qubits (which have similar frequencies)
    are never calibrated simultaneously.

    MUX internal layout (2x2):
        4N   4N+1
        4N+2 4N+3

    Ordering pattern:
        - Even MUX (mux_id % 2 == 0): [0, 1, 2, 3] offset order
        - Odd MUX (mux_id % 2 == 1): [2, 3, 0, 1] offset order

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
        # Determine which offset order to use
        if mux_id % 2 == 0:
            offset_order = self.EVEN_MUX_ORDER
        else:
            offset_order = self.ODD_MUX_ORDER

        # Base qubit ID for this MUX
        base_qid = mux_id * 4

        # Build mapping from offset to qid
        qid_set = set(qids)
        ordered = []

        for offset in offset_order:
            target_qid = str(base_qid + offset)
            if target_qid in qid_set:
                ordered.append(target_qid)

        return ordered

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
        steps: list[list[str]] = [[] for _ in range(4)]

        for mux_id in sorted(mux_ids):
            base_qid = mux_id * 4

            # Determine offset order for this MUX
            if mux_id % 2 == 0:
                offset_order = self.EVEN_MUX_ORDER
            else:
                offset_order = self.ODD_MUX_ORDER

            # Add qubits to corresponding steps
            for step_idx, offset in enumerate(offset_order):
                target_qid = str(base_qid + offset)
                if target_qid in qid_set:
                    steps[step_idx].append(target_qid)

        # Filter out empty steps
        return [step for step in steps if step]


class DefaultSynchronizedStrategy(MuxOrderingStrategy):
    """Default strategy for synchronized step generation.

    Uses natural ordering [0, 1, 2, 3] for all MUXes, generating 4 synchronized
    steps without frequency-aware optimization.

    Example:
        For MUXes [0, 1]:
        - Step 0: [0, 4]  (offset 0 from each MUX)
        - Step 1: [1, 5]  (offset 1 from each MUX)
        - Step 2: [2, 6]  (offset 2 from each MUX)
        - Step 3: [3, 7]  (offset 3 from each MUX)
    """

    def order_qids_in_mux(
        self,
        mux_id: int,
        qids: list[str],
        context: OrderingContext,
    ) -> list[str]:
        """Return qubits in natural order."""
        return sorted(qids, key=lambda x: int(x))

    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata."""
        return {
            "strategy_name": "default_synchronized",
            "description": "Natural order synchronized steps",
        }

    def generate_synchronized_steps(
        self,
        mux_ids: list[int],
        qids: list[str],
        context: OrderingContext,
    ) -> list[list[str]]:
        """Generate synchronized steps with natural ordering.

        Args:
            mux_ids: List of MUX IDs to include
            qids: List of all qubit IDs
            context: Context object

        Returns:
            List of 4 steps with natural ordering
        """
        qid_set = set(qids)
        steps: list[list[str]] = [[] for _ in range(4)]

        for mux_id in sorted(mux_ids):
            base_qid = mux_id * 4

            for offset in range(4):
                target_qid = str(base_qid + offset)
                if target_qid in qid_set:
                    steps[offset].append(target_qid)

        return [step for step in steps if step]

    def __repr__(self) -> str:
        """String representation."""
        return "DefaultSynchronizedStrategy()"
