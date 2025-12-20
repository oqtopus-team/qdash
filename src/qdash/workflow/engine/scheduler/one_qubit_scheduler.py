"""1-Qubit Calibration Scheduler for Workflow Engine.

This module provides scheduling for 1-qubit calibration based on box (筐体) constraints.
Different box types (Type A, Type B) cannot execute simultaneously, so qubits must be
grouped by their box dependencies.

Box Detection:
    The scheduler analyzes wiring configuration to determine box dependencies:
    - Module names ending with 'A' (e.g., "Q73A", "R20A") belong to Box A
    - Module names ending with 'B' (e.g., "R21B", "U10B") belong to Box B
    - MUXes using modules from both box types cannot run in parallel with either

Conflict Rules:
    - Qubits using the same box cannot execute in parallel (sequential within stage)
    - Qubits using different boxes can execute in parallel (different stages)
    - MUXes with mixed box dependencies conflict with both Box A and Box B

Parallel Groups:
    Within each stage, qubits are grouped by MUX for parallel execution:
    - Qubits on different MUXes can run in parallel
    - Qubits on the same MUX run sequentially (due to hardware constraints)
    - The `parallel_groups` field contains these MUX-based groups

Example:
    Basic usage in a calibration flow:

    ```python
    from qdash.workflow.engine.scheduler import OneQubitScheduler

    scheduler = OneQubitScheduler(chip_id="64Qv3")

    # Generate schedule from qubit IDs
    schedule = scheduler.generate(qids=["0", "1", "2", "3", "16", "17"])

    # Access results with parallel groups
    for stage in schedule.stages:
        print(f"Stage {stage.box_type}: {len(stage.parallel_groups)} parallel groups")
        # Execute parallel groups concurrently
        for group in stage.parallel_groups:
            # Qubits within each group run sequentially
            for qid in group:
                calibrate_qubit(qid)
    ```
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from qdash.workflow.engine.scheduler.one_qubit_plugins import (
        MuxOrderingStrategy,
    )

logger = logging.getLogger(__name__)


# Box type constants
BOX_A = "A"
BOX_B = "B"
BOX_MIXED = "MIXED"  # Uses both A and B


@dataclass
class OneQubitStageInfo:
    """Information about a single execution stage.

    Attributes:
        box_type: Type of box ("A", "B", or "MIXED")
        qids: List of qubit IDs in this stage (executed sequentially if not using parallel_groups)
        mux_ids: Set of MUX IDs included in this stage
        parallel_groups: MUX-based parallel groups. Each group (list of qids) can run in parallel
                        with other groups, but qubits within the same group run sequentially.
                        Format: [[mux0_qids], [mux1_qids], ...]
    """

    box_type: str
    qids: list[str]
    mux_ids: set[int] = field(default_factory=set)
    parallel_groups: list[list[str]] = field(default_factory=list)

    def __repr__(self) -> str:
        """String representation."""
        return f"Stage(type={self.box_type}, qids={self.qids}, parallel_groups={len(self.parallel_groups)})"


@dataclass
class OneQubitScheduleResult:
    """Result object containing 1-qubit schedule and metadata.

    Attributes:
        stages: List of execution stages (executed sequentially between stages,
                qubits within each stage also executed sequentially due to box constraints)
        metadata: Statistics about the schedule
        mux_box_map: Mapping from MUX ID to box type(s)
        qid_to_mux: Mapping from qubit ID to MUX ID
    """

    stages: list[OneQubitStageInfo]
    metadata: dict[str, Any]
    mux_box_map: dict[int, set[str]]
    qid_to_mux: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for serialization."""
        return {
            "stages": [
                {
                    "box_type": stage.box_type,
                    "qids": stage.qids,
                    "mux_ids": list(stage.mux_ids),
                    "parallel_groups": stage.parallel_groups,
                }
                for stage in self.stages
            ],
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        """String representation."""
        total_qubits = sum(len(stage.qids) for stage in self.stages)
        return f"OneQubitScheduleResult(qubits={total_qubits}, stages={len(self.stages)})"


@dataclass
class SynchronizedStepInfo:
    """Information about a single synchronized execution step.

    Each step contains qubits that can be executed simultaneously across
    all participating MUXes.

    Attributes:
        step_index: Index of this step within the stage (0-3)
        box_type: Type of box ("A", "B", or "MIXED")
        parallel_qids: List of qubit IDs to execute simultaneously in this step
    """

    step_index: int
    box_type: str
    parallel_qids: list[str]

    def __repr__(self) -> str:
        """String representation."""
        return f"Step({self.step_index}, {self.box_type}, qids={len(self.parallel_qids)})"


@dataclass
class SynchronizedOneQubitScheduleResult:
    """Result object for synchronized 1-qubit scheduling.

    This result format provides step-based parallelism where each step contains
    qubits that can be executed simultaneously. Unlike the original format where
    MUXes execute independently, this ensures all MUXes are synchronized at each step.

    Structure:
        - steps: List of synchronized steps, each with qubits to execute in parallel
        - Grouped by box_type (A, B, MIXED) - execute stages sequentially
        - Within each box stage, execute steps sequentially
        - Within each step, execute all qubits in parallel

    Execution Flow:
        For Box A with checkerboard strategy:
        - Step 1: Execute [0, 6, 8, 14, ...] simultaneously (16 qubits)
        - Step 2: Execute [1, 7, 9, 15, ...] simultaneously (16 qubits)
        - Step 3: Execute [2, 4, 10, 12, ...] simultaneously (16 qubits)
        - Step 4: Execute [3, 5, 11, 13, ...] simultaneously (16 qubits)

    Attributes:
        steps: List of synchronized steps grouped by box type
        metadata: Statistics about the schedule
        mux_box_map: Mapping from MUX ID to box type(s)
        qid_to_mux: Mapping from qubit ID to MUX ID
    """

    steps: list[SynchronizedStepInfo]
    metadata: dict[str, Any]
    mux_box_map: dict[int, set[str]]
    qid_to_mux: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for serialization."""
        return {
            "steps": [
                {
                    "step_index": step.step_index,
                    "box_type": step.box_type,
                    "parallel_qids": step.parallel_qids,
                }
                for step in self.steps
            ],
            "metadata": self.metadata,
        }

    def get_steps_by_box(self, box_type: str) -> list[SynchronizedStepInfo]:
        """Get steps for a specific box type.

        Args:
            box_type: "A", "B", or "MIXED"

        Returns:
            List of steps for the specified box type
        """
        return [step for step in self.steps if step.box_type == box_type]

    @property
    def total_steps(self) -> int:
        """Total number of synchronized steps."""
        return len(self.steps)

    @property
    def box_types(self) -> list[str]:
        """List of unique box types in execution order."""
        seen = []
        for step in self.steps:
            if step.box_type not in seen:
                seen.append(step.box_type)
        return seen

    def __repr__(self) -> str:
        """String representation."""
        total_qubits = sum(len(step.parallel_qids) for step in self.steps)
        return f"SynchronizedOneQubitScheduleResult(qubits={total_qubits}, steps={len(self.steps)})"


class OneQubitScheduler:
    """1-Qubit Calibration Scheduler.

    Generates optimized scheduling for 1-qubit calibration operations based on
    box (筐体) constraints:
    - Box A: Modules with names ending in 'A'
    - Box B: Modules with names ending in 'B'
    - MUXes using both types cannot run in parallel with either

    Example:
        ```python
        scheduler = OneQubitScheduler(chip_id="64Qv3")

        # Generate schedule for specific qubits
        schedule = scheduler.generate(qids=["0", "1", "2", "3"])

        # Access stages
        for stage in schedule.stages:
            print(f"Box {stage.box_type}: {stage.qids}")

        # Check metadata
        print(f"Box A qubits: {schedule.metadata['box_a_count']}")
        print(f"Box B qubits: {schedule.metadata['box_b_count']}")
        ```
    """

    def __init__(
        self,
        chip_id: str,
        wiring_config_path: str | Path | None = None,
    ) -> None:
        """Initialize 1-qubit scheduler.

        Args:
            chip_id: Chip ID (e.g., "64Qv3", "144Qv2")
            wiring_config_path: Path to wiring.yaml configuration file.
                If None, uses default path: /workspace/qdash/config/qubex/{chip_id}/config/wiring.yaml
        """
        self.chip_id = chip_id
        self.wiring_config_path = wiring_config_path
        self._wiring_config: list[dict[str, Any]] | None = None
        self._mux_box_map: dict[int, set[str]] | None = None
        self._qid_to_mux: dict[str, int] | None = None
        self._box_b_module_to_muxes: dict[str, list[int]] | None = None

    def _load_wiring_config(self) -> list[dict[str, Any]]:
        """Load wiring configuration from YAML file."""
        if self._wiring_config is None:
            if self.wiring_config_path is not None:
                wiring_path = Path(self.wiring_config_path)
            else:
                wiring_path = Path(
                    f"/workspace/qdash/config/qubex/{self.chip_id}/config/wiring.yaml"
                )

            if not wiring_path.exists():
                msg = f"Wiring config not found: {wiring_path}"
                raise FileNotFoundError(msg)

            yaml_data = yaml.safe_load(wiring_path.read_text())
            self._wiring_config = yaml_data[self.chip_id]

        return self._wiring_config

    @staticmethod
    def _extract_box_type(module_name: str) -> str | None:
        """Extract box type from module name.

        Module naming convention:
        - Names ending with 'A' followed by optional suffix → Box A (e.g., "Q73A", "R20A-5")
        - Names ending with 'B' followed by optional suffix → Box B (e.g., "R21B", "U10B-0")

        Args:
            module_name: Module name from wiring config (e.g., "R21B-5", "Q73A-1")

        Returns:
            "A" for Box A, "B" for Box B, or None if unrecognized
        """
        # Extract the module identifier (part before the channel number)
        # e.g., "R21B-5" → "R21B", "Q73A-1" → "Q73A"
        match = re.match(r"^([A-Za-z0-9]+)(?:-\d+)?$", module_name)
        if not match:
            return None

        module_id = match.group(1)

        # Check the last character of the module identifier
        if module_id.endswith("A"):
            return BOX_A
        elif module_id.endswith("B"):
            return BOX_B

        return None

    def _build_mux_box_map(self, wiring_config: list[dict[str, Any]]) -> dict[int, set[str]]:
        """Build mapping from MUX ID to box types used.

        A MUX may use modules from one or both box types.

        Args:
            wiring_config: List of MUX configurations from wiring.yaml

        Returns:
            Mapping from MUX ID to set of box types ("A", "B", or both)
        """
        if self._mux_box_map is not None:
            return self._mux_box_map

        mux_box_map: dict[int, set[str]] = {}

        for mux_entry in wiring_config:
            mux_id = mux_entry["mux"]
            box_types: set[str] = set()

            # Check ctrl modules
            for ctrl in mux_entry.get("ctrl", []):
                box = self._extract_box_type(ctrl)
                if box:
                    box_types.add(box)

            # Check read_out module
            read_out = mux_entry.get("read_out")
            if read_out:
                box = self._extract_box_type(read_out)
                if box:
                    box_types.add(box)

            # Check read_in module
            read_in = mux_entry.get("read_in")
            if read_in:
                box = self._extract_box_type(read_in)
                if box:
                    box_types.add(box)

            # Check pump module
            pump = mux_entry.get("pump")
            if pump:
                box = self._extract_box_type(pump)
                if box:
                    box_types.add(box)

            mux_box_map[mux_id] = box_types

        self._mux_box_map = mux_box_map
        return mux_box_map

    def _build_qubit_to_mux_map(self, wiring_config: list[dict[str, Any]]) -> dict[str, int]:
        """Build mapping from qubit ID to MUX ID.

        Each MUX controls 4 qubits: MUX_N controls qubits [4N, 4N+1, 4N+2, 4N+3].

        Args:
            wiring_config: List of MUX configurations from wiring.yaml

        Returns:
            Mapping from qubit ID (string) to MUX ID (int)
        """
        if self._qid_to_mux is not None:
            return self._qid_to_mux

        qid_to_mux = {}
        for entry in wiring_config:
            mux_id = entry["mux"]
            for offset in range(4):
                qid_to_mux[str(mux_id * 4 + offset)] = mux_id

        self._qid_to_mux = qid_to_mux
        return qid_to_mux

    @staticmethod
    def _extract_module_id(module_name: str) -> str | None:
        """Extract module identifier from module name.

        Args:
            module_name: Full module name (e.g., "R21B-5", "Q73A-1")

        Returns:
            Module identifier without channel (e.g., "R21B", "Q73A")
        """
        match = re.match(r"^([A-Za-z0-9]+)(?:-\d+)?$", module_name)
        if match:
            return match.group(1)
        return None

    def _build_box_b_module_map(self, wiring_config: list[dict[str, Any]]) -> dict[str, list[int]]:
        """Build mapping from Box B module to MUX IDs that use it.

        Box B modules control 8 qubits (2 MUXes). MUXes sharing the same
        Box B module cannot execute in parallel.

        Args:
            wiring_config: List of MUX configurations from wiring.yaml

        Returns:
            Mapping from Box B module ID to list of MUX IDs using it

        Example:
            {"R21B": [0, 4], "U10B": [3, 7], "U13B": [10, 14]}
        """
        if self._box_b_module_to_muxes is not None:
            return self._box_b_module_to_muxes

        box_b_to_muxes: dict[str, list[int]] = {}

        for mux_entry in wiring_config:
            mux_id = mux_entry["mux"]

            # Check ctrl modules for Box B
            for ctrl in mux_entry.get("ctrl", []):
                module_id = self._extract_module_id(ctrl)
                if module_id and module_id.endswith("B"):
                    if module_id not in box_b_to_muxes:
                        box_b_to_muxes[module_id] = []
                    if mux_id not in box_b_to_muxes[module_id]:
                        box_b_to_muxes[module_id].append(mux_id)

        # Sort MUX IDs for deterministic ordering
        for module_id in box_b_to_muxes:
            box_b_to_muxes[module_id].sort()

        self._box_b_module_to_muxes = box_b_to_muxes
        return box_b_to_muxes

    def _group_mixed_muxes_by_box_b(
        self,
        mixed_mux_ids: list[int],
        box_b_module_map: dict[str, list[int]],
    ) -> list[list[int]]:
        """Group MIXED MUXes by Box B module for sequential execution.

        MUXes sharing the same Box B module must execute in separate groups
        (cannot run in parallel).

        Args:
            mixed_mux_ids: List of MIXED MUX IDs to group
            box_b_module_map: Mapping from Box B module to MUX IDs

        Returns:
            List of MUX ID groups. Each group can run in parallel,
            but groups must execute sequentially.

        Example:
            Input: [0, 3, 4, 7] with R21B→[0,4], U10B→[3,7]
            Output: [[0, 3], [4, 7]]
            - Group 0: MUX 0 (R21B first), MUX 3 (U10B first)
            - Group 1: MUX 4 (R21B second), MUX 7 (U10B second)
        """
        if not mixed_mux_ids:
            return []

        mixed_set = set(mixed_mux_ids)

        # Build reverse map: MUX → Box B module
        mux_to_box_b: dict[int, str] = {}
        for module_id, mux_ids in box_b_module_map.items():
            for mux_id in mux_ids:
                if mux_id in mixed_set:
                    mux_to_box_b[mux_id] = module_id

        # Find the maximum group index needed
        max_group_idx = 0
        for module_id, mux_ids in box_b_module_map.items():
            count = sum(1 for m in mux_ids if m in mixed_set)
            max_group_idx = max(max_group_idx, count)

        if max_group_idx == 0:
            # No Box B sharing, all can run in parallel
            return [list(mixed_mux_ids)]

        # Assign each MUX to a group based on its position in the Box B module
        groups: list[list[int]] = [[] for _ in range(max_group_idx)]

        for module_id, mux_ids in box_b_module_map.items():
            relevant_muxes = [m for m in mux_ids if m in mixed_set]
            for idx, mux_id in enumerate(relevant_muxes):
                groups[idx].append(mux_id)

        # Sort MUXes within each group
        for group in groups:
            group.sort()

        # Filter out empty groups
        return [g for g in groups if g]

    def _group_qids_by_mux(
        self,
        qids: list[str],
        qid_to_mux: dict[str, int],
        ordering_strategy: MuxOrderingStrategy | None = None,
    ) -> list[list[str]]:
        """Group qubit IDs by their MUX for parallel execution.

        Qubits on different MUXes can run in parallel, while qubits on the
        same MUX must run sequentially.

        Args:
            qids: List of qubit IDs to group
            qid_to_mux: Mapping from qubit ID to MUX ID
            ordering_strategy: Optional strategy for ordering qubits within each MUX.
                If None, uses natural qubit ID order.

        Returns:
            List of qubit groups, where each group contains qubits from the same MUX.
            Groups are sorted by MUX ID for deterministic ordering.
        """
        from qdash.workflow.engine.scheduler.one_qubit_plugins import (
            OrderingContext,
        )

        mux_groups: dict[int, list[str]] = {}
        for qid in qids:
            mux_id = qid_to_mux.get(qid, int(qid) // 4)  # Default: 4 qubits per MUX
            if mux_id not in mux_groups:
                mux_groups[mux_id] = []
            mux_groups[mux_id].append(qid)

        # Apply ordering strategy if provided
        if ordering_strategy is not None:
            # Determine grid size from chip_id
            if "144" in self.chip_id:
                grid_size = 12
            else:
                grid_size = 8
            mux_grid_size = grid_size // 2

            context = OrderingContext(
                chip_id=self.chip_id,
                grid_size=grid_size,
                mux_grid_size=mux_grid_size,
                qid_to_mux=qid_to_mux,
            )

            for mux_id in mux_groups:
                mux_groups[mux_id] = ordering_strategy.order_qids_in_mux(
                    mux_id, mux_groups[mux_id], context
                )
        else:
            # Default: sort by qubit ID
            for mux_id in mux_groups:
                mux_groups[mux_id] = sorted(mux_groups[mux_id], key=lambda x: int(x))

        # Return groups sorted by MUX ID
        return [mux_groups[mux_id] for mux_id in sorted(mux_groups.keys())]

    def _get_qubit_box_type(
        self,
        qid: str,
        qid_to_mux: dict[str, int],
        mux_box_map: dict[int, set[str]],
    ) -> str:
        """Get box type for a qubit.

        Args:
            qid: Qubit ID
            qid_to_mux: Mapping from qubit ID to MUX ID
            mux_box_map: Mapping from MUX ID to box types

        Returns:
            "A" for Box A only, "B" for Box B only, "MIXED" for both
        """
        if qid not in qid_to_mux:
            logger.warning(f"Qubit {qid} not found in MUX mapping")
            return BOX_MIXED  # Conservative: treat as conflicting with both

        mux_id = qid_to_mux[qid]
        box_types = mux_box_map.get(mux_id, set())

        if len(box_types) == 0:
            logger.warning(f"MUX {mux_id} has no detected box types")
            return BOX_MIXED
        elif len(box_types) == 1:
            return next(iter(box_types))
        else:
            return BOX_MIXED

    def generate(
        self,
        qids: list[str],
        ordering_strategy: MuxOrderingStrategy | None = None,
    ) -> OneQubitScheduleResult:
        """Generate 1-qubit execution schedule.

        Groups qubits into stages based on box constraints:
        - Box A only qubits → Box A stage
        - Box B only qubits → Box B stage
        - Mixed qubits → Executed last (conflicts with both)

        Within each stage, qubits are executed sequentially due to
        same-box resource conflicts.

        Args:
            qids: List of qubit IDs to schedule
            ordering_strategy: Optional strategy for ordering qubits within each MUX.
                Use CheckerboardOrderingStrategy for frequency-aware ordering.
                If None, uses natural qubit ID order.

        Returns:
            OneQubitScheduleResult containing stages and metadata

        Raises:
            FileNotFoundError: If wiring configuration not found
            ValueError: If no valid qubits provided

        Example:
            ```python
            scheduler = OneQubitScheduler(chip_id="64Qv3")
            schedule = scheduler.generate(qids=["0", "1", "4", "5", "16", "17"])

            # Execute stages
            for stage in schedule.stages:
                for qid in stage.qids:
                    calibrate_qubit(qid)

            # With frequency-aware ordering
            from qdash.workflow.engine.scheduler.one_qubit_plugins import (
                CheckerboardOrderingStrategy,
            )
            schedule = scheduler.generate(
                qids=["0", "1", "4", "5"],
                ordering_strategy=CheckerboardOrderingStrategy(),
            )
            ```
        """
        logger.info(f"Generating 1-qubit schedule for chip_id={self.chip_id}")
        logger.info(f"  Input qubits: {qids}")

        if len(qids) == 0:
            msg = "No qubits provided"
            raise ValueError(msg)

        # Load configuration
        wiring_config = self._load_wiring_config()
        mux_box_map = self._build_mux_box_map(wiring_config)
        qid_to_mux = self._build_qubit_to_mux_map(wiring_config)

        # Classify qubits by box type
        box_a_qids: list[str] = []
        box_b_qids: list[str] = []
        mixed_qids: list[str] = []

        for qid in qids:
            box_type = self._get_qubit_box_type(qid, qid_to_mux, mux_box_map)
            if box_type == BOX_A:
                box_a_qids.append(qid)
            elif box_type == BOX_B:
                box_b_qids.append(qid)
            else:
                mixed_qids.append(qid)

        logger.info(f"  Box A qubits: {box_a_qids}")
        logger.info(f"  Box B qubits: {box_b_qids}")
        logger.info(f"  Mixed qubits: {mixed_qids}")

        # Build stages with parallel groups
        stages: list[OneQubitStageInfo] = []

        if box_a_qids:
            mux_ids = {qid_to_mux[qid] for qid in box_a_qids if qid in qid_to_mux}
            parallel_groups = self._group_qids_by_mux(box_a_qids, qid_to_mux, ordering_strategy)
            stages.append(
                OneQubitStageInfo(
                    box_type=BOX_A,
                    qids=box_a_qids,
                    mux_ids=mux_ids,
                    parallel_groups=parallel_groups,
                )
            )

        if box_b_qids:
            mux_ids = {qid_to_mux[qid] for qid in box_b_qids if qid in qid_to_mux}
            parallel_groups = self._group_qids_by_mux(box_b_qids, qid_to_mux, ordering_strategy)
            stages.append(
                OneQubitStageInfo(
                    box_type=BOX_B,
                    qids=box_b_qids,
                    mux_ids=mux_ids,
                    parallel_groups=parallel_groups,
                )
            )

        # Mixed qubits need to run separately (conflict with both box types)
        if mixed_qids:
            mux_ids = {qid_to_mux[qid] for qid in mixed_qids if qid in qid_to_mux}
            parallel_groups = self._group_qids_by_mux(mixed_qids, qid_to_mux, ordering_strategy)
            stages.append(
                OneQubitStageInfo(
                    box_type=BOX_MIXED,
                    qids=mixed_qids,
                    mux_ids=mux_ids,
                    parallel_groups=parallel_groups,
                )
            )

        logger.info(f"Generated {len(stages)} stages")
        for i, stage in enumerate(stages, 1):
            logger.info(
                f"  Stage {i} ({stage.box_type}): {len(stage.qids)} qubits, {len(stage.parallel_groups)} parallel groups"
            )

        # Build metadata
        metadata = {
            "total_qubits": len(qids),
            "box_a_count": len(box_a_qids),
            "box_b_count": len(box_b_qids),
            "mixed_count": len(mixed_qids),
            "num_stages": len(stages),
            "chip_id": self.chip_id,
        }

        return OneQubitScheduleResult(
            stages=stages,
            metadata=metadata,
            mux_box_map=mux_box_map,
            qid_to_mux=qid_to_mux,
        )

    def generate_from_mux(
        self,
        mux_ids: list[int],
        exclude_qids: list[str] | None = None,
        ordering_strategy: MuxOrderingStrategy | None = None,
    ) -> OneQubitScheduleResult:
        """Generate 1-qubit execution schedule from MUX IDs.

        Convenience method that converts MUX IDs to qubit IDs and generates schedule.
        Each MUX controls 4 qubits: MUX_N → qubits [4N, 4N+1, 4N+2, 4N+3].

        Args:
            mux_ids: List of MUX IDs to schedule
            exclude_qids: Optional list of qubit IDs to exclude from scheduling
            ordering_strategy: Optional strategy for ordering qubits within each MUX.
                Use CheckerboardOrderingStrategy for frequency-aware ordering.
                If None, uses natural qubit ID order.

        Returns:
            OneQubitScheduleResult containing stages and metadata

        Raises:
            FileNotFoundError: If wiring configuration not found
            ValueError: If no valid MUX IDs provided or all qubits excluded

        Example:
            ```python
            scheduler = OneQubitScheduler(chip_id="64Qv3")

            # Schedule MUXes 0, 1 but exclude qubits 2 and 5
            schedule = scheduler.generate_from_mux(
                mux_ids=[0, 1],
                exclude_qids=["2", "5"]
            )
            # Results in qids: ["0", "1", "3", "4", "6", "7"]

            for stage in schedule.stages:
                print(f"Stage {stage.box_type}: {stage.qids}")

            # With frequency-aware ordering
            from qdash.workflow.engine.scheduler.one_qubit_plugins import (
                CheckerboardOrderingStrategy,
            )
            schedule = scheduler.generate_from_mux(
                mux_ids=[0, 1, 2, 3],
                ordering_strategy=CheckerboardOrderingStrategy(),
            )
            ```
        """
        if len(mux_ids) == 0:
            msg = "No MUX IDs provided"
            raise ValueError(msg)

        # Convert MUX IDs to qubit IDs
        qids = []
        for mux_id in mux_ids:
            for offset in range(4):
                qids.append(str(mux_id * 4 + offset))

        # Exclude specified qubit IDs
        if exclude_qids:
            exclude_set = set(exclude_qids)
            original_count = len(qids)
            qids = [qid for qid in qids if qid not in exclude_set]
            excluded_count = original_count - len(qids)
            logger.info(
                f"Excluded {excluded_count} qubits: {sorted(exclude_set & set(str(mux_id * 4 + o) for mux_id in mux_ids for o in range(4)))}"
            )

            if len(qids) == 0:
                msg = "All qubits were excluded"
                raise ValueError(msg)

        logger.info(f"Converting {len(mux_ids)} MUX IDs to {len(qids)} qubit IDs")
        return self.generate(qids=qids, ordering_strategy=ordering_strategy)

    def get_mux_info(self) -> dict[int, dict[str, Any]]:
        """Get detailed MUX information with box classification.

        Useful for debugging and visualization.

        Returns:
            Mapping from MUX ID to info dict containing:
            - box_types: Set of box types used
            - qids: List of qubit IDs controlled by this MUX
            - box_label: Human-readable label ("A", "B", or "A+B")
        """
        wiring_config = self._load_wiring_config()
        mux_box_map = self._build_mux_box_map(wiring_config)
        qid_to_mux = self._build_qubit_to_mux_map(wiring_config)

        # Invert qid_to_mux to get mux_to_qids
        mux_to_qids: dict[int, list[str]] = {}
        for qid, mux_id in qid_to_mux.items():
            if mux_id not in mux_to_qids:
                mux_to_qids[mux_id] = []
            mux_to_qids[mux_id].append(qid)

        result = {}
        for mux_id, box_types in mux_box_map.items():
            if len(box_types) == 1:
                label = next(iter(box_types))
            elif len(box_types) == 2:
                label = "A+B"
            else:
                label = "?"

            result[mux_id] = {
                "box_types": box_types,
                "qids": sorted(mux_to_qids.get(mux_id, []), key=int),
                "box_label": label,
            }

        return result

    def generate_synchronized(
        self,
        qids: list[str],
        use_checkerboard: bool = True,
    ) -> SynchronizedOneQubitScheduleResult:
        """Generate synchronized 1-qubit execution schedule.

        This method creates a step-based schedule where each step contains
        qubits that execute simultaneously across all MUXes. This ensures
        true synchronization between MUXes at each step.

        Unlike the original `generate()` method where MUXes execute independently,
        this method guarantees that all MUXes complete step N before any MUX
        starts step N+1.

        Execution pattern (with checkerboard strategy):
            Box A (4 steps):
                Step 0: [0, 6, 8, 14, 16, 22, ...] - all simultaneously
                Step 1: [1, 7, 9, 15, 17, 23, ...] - all simultaneously
                Step 2: [2, 4, 10, 12, 18, 20, ...] - all simultaneously
                Step 3: [3, 5, 11, 13, 19, 21, ...] - all simultaneously

            Box Mixed (4 steps):
                Step 0-3: Similar pattern for MIXED MUXes

        Args:
            qids: List of qubit IDs to schedule
            use_checkerboard: If True, uses CheckerboardOrderingStrategy for
                frequency isolation. If False, uses natural order.

        Returns:
            SynchronizedOneQubitScheduleResult containing steps and metadata

        Raises:
            FileNotFoundError: If wiring configuration not found
            ValueError: If no valid qubits provided

        Example:
            ```python
            scheduler = OneQubitScheduler(chip_id="64Qv3")

            # Generate synchronized schedule with checkerboard pattern
            schedule = scheduler.generate_synchronized(
                qids=[str(i) for i in range(64)],
                use_checkerboard=True,
            )

            # Execute all steps
            for step in schedule.steps:
                # Execute all qubits in step.parallel_qids simultaneously
                execute_parallel(step.parallel_qids)

            # Total steps: ~12 (4 for Box A + 4 for Box B + 4 for MIXED)
            print(f"Total steps: {schedule.total_steps}")
            ```
        """
        from qdash.workflow.engine.scheduler.one_qubit_plugins import (
            CheckerboardOrderingStrategy,
            DefaultSynchronizedStrategy,
            OrderingContext,
        )

        logger.info(f"Generating synchronized 1-qubit schedule for chip_id={self.chip_id}")
        logger.info(f"  Input qubits: {len(qids)} qubits")
        logger.info(f"  Checkerboard: {use_checkerboard}")

        if len(qids) == 0:
            msg = "No qubits provided"
            raise ValueError(msg)

        # Load configuration
        wiring_config = self._load_wiring_config()
        mux_box_map = self._build_mux_box_map(wiring_config)
        qid_to_mux = self._build_qubit_to_mux_map(wiring_config)

        # Determine grid size from chip_id
        if "144" in self.chip_id:
            grid_size = 12
        else:
            grid_size = 8
        mux_grid_size = grid_size // 2

        # Create ordering context
        context = OrderingContext(
            chip_id=self.chip_id,
            grid_size=grid_size,
            mux_grid_size=mux_grid_size,
            qid_to_mux=qid_to_mux,
        )

        # Select strategy
        if use_checkerboard:
            strategy = CheckerboardOrderingStrategy()
        else:
            strategy = DefaultSynchronizedStrategy()

        # Classify qubits by box type
        box_a_qids: list[str] = []
        box_b_qids: list[str] = []
        mixed_qids: list[str] = []

        for qid in qids:
            box_type = self._get_qubit_box_type(qid, qid_to_mux, mux_box_map)
            if box_type == BOX_A:
                box_a_qids.append(qid)
            elif box_type == BOX_B:
                box_b_qids.append(qid)
            else:
                mixed_qids.append(qid)

        logger.info(f"  Box A qubits: {len(box_a_qids)}")
        logger.info(f"  Box B qubits: {len(box_b_qids)}")
        logger.info(f"  Mixed qubits: {len(mixed_qids)}")

        # Build synchronized steps
        all_steps: list[SynchronizedStepInfo] = []

        # Helper function to generate steps for a set of qubits
        def generate_steps_for_box(
            box_qids: list[str],
            box_type: str,
            base_step_index: int,
        ) -> list[SynchronizedStepInfo]:
            if not box_qids:
                return []

            # Get MUX IDs for these qubits
            mux_ids = sorted({qid_to_mux[qid] for qid in box_qids if qid in qid_to_mux})

            # Generate synchronized steps using the strategy
            raw_steps = strategy.generate_synchronized_steps(mux_ids, box_qids, context)

            steps = []
            for idx, parallel_qids in enumerate(raw_steps):
                steps.append(
                    SynchronizedStepInfo(
                        step_index=base_step_index + idx,
                        box_type=box_type,
                        parallel_qids=parallel_qids,
                    )
                )
            return steps

        # Generate steps for each box type (in order: A, B, MIXED)
        step_index = 0

        if box_a_qids:
            box_a_steps = generate_steps_for_box(box_a_qids, BOX_A, step_index)
            all_steps.extend(box_a_steps)
            step_index += len(box_a_steps)

        if box_b_qids:
            box_b_steps = generate_steps_for_box(box_b_qids, BOX_B, step_index)
            all_steps.extend(box_b_steps)
            step_index += len(box_b_steps)

        if mixed_qids:
            # MIXED MUXes need special handling due to Box B module sharing
            # MUXes sharing the same Box B module cannot run in parallel
            box_b_module_map = self._build_box_b_module_map(wiring_config)

            # Get MIXED MUX IDs
            mixed_mux_ids = sorted({qid_to_mux[qid] for qid in mixed_qids if qid in qid_to_mux})

            # Group MIXED MUXes by Box B module sharing
            mux_groups = self._group_mixed_muxes_by_box_b(mixed_mux_ids, box_b_module_map)

            logger.info(f"  MIXED MUX groups (Box B sharing): {mux_groups}")

            # Generate steps for each MIXED group sequentially
            # Each group gets 4 steps, so 2 groups = 8 steps total
            for group_idx, mux_group in enumerate(mux_groups):
                # Get qubits for this MUX group
                group_qids = [
                    qid for qid in mixed_qids if qid in qid_to_mux and qid_to_mux[qid] in mux_group
                ]

                if group_qids:
                    # Generate synchronized steps for this group
                    raw_steps = strategy.generate_synchronized_steps(mux_group, group_qids, context)

                    for idx, parallel_qids in enumerate(raw_steps):
                        all_steps.append(
                            SynchronizedStepInfo(
                                step_index=step_index,
                                box_type=BOX_MIXED,
                                parallel_qids=parallel_qids,
                            )
                        )
                        step_index += 1

        logger.info(f"Generated {len(all_steps)} synchronized steps")
        for step in all_steps:
            logger.info(
                f"  Step {step.step_index} ({step.box_type}): {len(step.parallel_qids)} qubits"
            )

        # Build metadata
        metadata = {
            "total_qubits": len(qids),
            "box_a_count": len(box_a_qids),
            "box_b_count": len(box_b_qids),
            "mixed_count": len(mixed_qids),
            "num_steps": len(all_steps),
            "chip_id": self.chip_id,
            "use_checkerboard": use_checkerboard,
            "strategy": strategy.get_metadata()["strategy_name"],
        }

        return SynchronizedOneQubitScheduleResult(
            steps=all_steps,
            metadata=metadata,
            mux_box_map=mux_box_map,
            qid_to_mux=qid_to_mux,
        )

    def generate_synchronized_from_mux(
        self,
        mux_ids: list[int],
        exclude_qids: list[str] | None = None,
        use_checkerboard: bool = True,
    ) -> SynchronizedOneQubitScheduleResult:
        """Generate synchronized schedule from MUX IDs.

        Convenience method that converts MUX IDs to qubit IDs and generates
        a synchronized schedule.

        Args:
            mux_ids: List of MUX IDs to schedule
            exclude_qids: Optional list of qubit IDs to exclude
            use_checkerboard: If True, uses CheckerboardOrderingStrategy

        Returns:
            SynchronizedOneQubitScheduleResult containing steps and metadata

        Raises:
            FileNotFoundError: If wiring configuration not found
            ValueError: If no valid MUX IDs provided or all qubits excluded

        Example:
            ```python
            scheduler = OneQubitScheduler(chip_id="64Qv3")

            # Schedule all 16 MUXes with checkerboard pattern
            schedule = scheduler.generate_synchronized_from_mux(
                mux_ids=list(range(16)),
                use_checkerboard=True,
            )

            # Results in ~12 steps (4 A + 4 B + 4 MIXED, depending on chip)
            for step in schedule.steps:
                print(f"Step {step.step_index}: {step.parallel_qids}")
            ```
        """
        if len(mux_ids) == 0:
            msg = "No MUX IDs provided"
            raise ValueError(msg)

        # Convert MUX IDs to qubit IDs
        qids = []
        for mux_id in mux_ids:
            for offset in range(4):
                qids.append(str(mux_id * 4 + offset))

        # Exclude specified qubit IDs
        if exclude_qids:
            exclude_set = set(exclude_qids)
            original_count = len(qids)
            qids = [qid for qid in qids if qid not in exclude_set]
            excluded_count = original_count - len(qids)
            logger.info(f"Excluded {excluded_count} qubits")

            if len(qids) == 0:
                msg = "All qubits were excluded"
                raise ValueError(msg)

        logger.info(f"Converting {len(mux_ids)} MUX IDs to {len(qids)} qubit IDs")
        return self.generate_synchronized(qids=qids, use_checkerboard=use_checkerboard)
