"""CR Gate Schedule Generator for Workflow Engine.

This module provides a clean API for generating optimized CR gate execution schedules
based on hardware constraints, qubit quality metrics, and MUX resource conflicts.

Direction Inference:
    The scheduler uses a two-tier approach for determining CR gate direction:

    1. **Design-based inference (default)**: Uses the checkerboard frequency pattern
       from chip design to infer direction without requiring calibrated frequency data.
       This is based on the square lattice topology where frequency is determined by
       coordinate parity: (row + col) % 2.

    2. **Measured directionality (fallback)**: Uses actual calibrated qubit frequencies
       when available. This provides more accurate direction but requires prior
       frequency calibration.

Example:
    Basic usage in a calibration flow:

    ```python
    from qdash.workflow.engine.cr_scheduler import CRScheduler

    scheduler = CRScheduler(username, chip_id)

    # Works without frequency calibration (uses design-based inference)
    schedule = scheduler.generate(max_parallel_ops=10)

    # Or with calibrated frequencies (uses measured directionality)
    # Run frequency calibration first, then generate schedule
    schedule = scheduler.generate(max_parallel_ops=10)

    # Use the schedule
    parallel_groups = schedule.parallel_groups  # [[(c, t), ...], ...]
    for group in parallel_groups:
        # Execute group in parallel
        pass
    ```
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
from qdash.workflow.engine.scheduler.cr_utils import (
    build_mux_conflict_map,
    build_qubit_to_mux_map,
    convert_to_parallel_groups,
    extract_qubit_frequency,
    group_cr_pairs_by_conflict,
    infer_direction_from_design,
    split_fast_slow_pairs,
)

if TYPE_CHECKING:
    from qdash.common.topology_config import TopologyDefinition
    from qdash.datamodel.chip import ChipModel
    from qdash.repository.protocols import ChipRepository

logger = logging.getLogger(__name__)


class CRScheduleResult:
    """Result object containing CR schedule and metadata.

    Attributes:
        parallel_groups: List of coupling groups for parallel execution.
            Format: [[(control, target), ...], ...]
        metadata: Statistics about the schedule (total_pairs, fast_pairs, etc.)
        filtering_stats: Filtering statistics (all_pairs, freq_filtered, etc.)
        cr_pairs_string: String representation of CR pairs (for internal use)
        qid_to_mux: Mapping from qubit ID to MUX ID
        mux_conflict_map: MUX conflict relationships
    """

    def __init__(
        self,
        parallel_groups: list[list[tuple[str, str]]],
        metadata: dict[str, Any],
        filtering_stats: dict[str, Any],
        cr_pairs_string: list[str],
        qid_to_mux: dict[str, int],
        mux_conflict_map: dict[int, set[int]],
    ) -> None:
        """Initialize schedule result."""
        self.parallel_groups = parallel_groups
        self.metadata = metadata
        self.filtering_stats = filtering_stats
        self._cr_pairs_string = cr_pairs_string
        self._qid_to_mux = qid_to_mux
        self._mux_conflict_map = mux_conflict_map

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for serialization."""
        return {
            "parallel_groups": self.parallel_groups,
            "metadata": self.metadata,
            "filtering_stats": self.filtering_stats,
        }

    def __repr__(self) -> str:
        """String representation."""
        total_pairs = self.metadata.get("scheduled_pairs", 0)
        num_groups = self.metadata.get("num_groups", 0)
        return f"CRScheduleResult(pairs={total_pairs}, groups={num_groups})"


class CRScheduler:
    """CR Gate Schedule Generator.

    Generates optimized scheduling for cross-resonance (CR) gate operations based on:
    - Frequency directionality constraints (design-based or measured)
    - MUX resource conflict detection
    - Greedy graph coloring for parallel grouping
    - Candidate qubit filtering

    Direction Determination:
        - **Design-based (default)**: Infers direction from checkerboard frequency pattern
          based on qubit coordinates. Works without calibrated frequency data.
        - **Measured (fallback)**: Uses actual calibrated qubit frequencies when available.
          Automatically selected when frequency calibration data exists.

    Example:
        ```python
        # Works even without frequency calibration data
        scheduler = CRScheduler(username="alice", chip_id="64Qv3")
        schedule = scheduler.generate()  # Uses design-based inference

        # After frequency calibration, automatically uses measured data
        # (run frequency calibration first)
        schedule = scheduler.generate()  # Uses measured directionality

        # Or specify custom wiring config path
        scheduler = CRScheduler(
            username="alice",
            chip_id="64Qv3",
            wiring_config_path="/custom/path/to/wiring.yaml"
        )
        schedule = scheduler.generate()

        # Check which method was used
        print(f"Direction method: {schedule.metadata['direction_method']}")
        print(f"Generated {len(schedule.parallel_groups)} groups")
        for i, group in enumerate(schedule.parallel_groups, 1):
            print(f"Group {i}: {len(group)} pairs")
        ```
    """

    def __init__(
        self,
        username: str,
        chip_id: str,
        wiring_config_path: str | Path | None = None,
        *,
        chip_repo: ChipRepository | None = None,
    ) -> None:
        """Initialize CR scheduler.

        Args:
            username: Username for chip data access
            chip_id: Chip ID
            wiring_config_path: Path to wiring.yaml configuration file.
                If None, uses the default QubexPaths wiring path.
            chip_repo: Repository for chip data access.
                If None, uses MongoChipRepository.

        """
        self.username = username
        self.chip_id = chip_id
        self.wiring_config_path = wiring_config_path
        self._chip_repo = chip_repo
        self._chip: ChipModel | None = None
        self._wiring_config: list[dict[str, Any]] | None = None
        self._topology: TopologyDefinition | None = None
        # Cached individual document data (scalable approach for 256+ qubits)
        self._qubit_models: dict[str, Any] | None = None
        self._coupling_ids: list[str] | None = None

    def _ensure_chip_repo(self) -> ChipRepository:
        """Ensure chip repository is initialized."""
        if self._chip_repo is None:
            from qdash.repository import MongoChipRepository

            self._chip_repo = MongoChipRepository()
        return self._chip_repo

    def _load_chip_data(self) -> ChipModel:
        """Load chip data from database."""
        if self._chip is None:
            chip_repo = self._ensure_chip_repo()
            chip = chip_repo.get_current_chip(self.username)
            if chip is None:
                raise ValueError(f"Chip not found for user {self.username}")
            self._chip = chip
        return self._chip

    def _load_qubit_models(self) -> dict[str, Any]:
        """Load qubit models from individual QubitDocument collection (scalable)."""
        if self._qubit_models is None:
            chip_repo = self._ensure_chip_repo()
            # Get project_id from chip metadata
            chip = self._load_chip_data()
            project_id = chip.project_id
            if project_id is None:
                raise ValueError(f"Chip {self.chip_id} has no project_id")
            self._qubit_models = chip_repo.get_all_qubit_models(project_id, self.chip_id)
        return self._qubit_models

    def _load_coupling_ids(self) -> list[str]:
        """Load coupling IDs from individual CouplingDocument collection (scalable)."""
        if self._coupling_ids is None:
            chip_repo = self._ensure_chip_repo()
            # Get project_id from chip metadata
            chip = self._load_chip_data()
            project_id = chip.project_id
            if project_id is None:
                raise ValueError(f"Chip {self.chip_id} has no project_id")
            self._coupling_ids = chip_repo.get_coupling_ids(project_id, self.chip_id)
        return self._coupling_ids

    def _load_topology(self) -> TopologyDefinition | None:
        """Load topology from chip's topology_id."""
        if self._topology is None:
            chip = self._load_chip_data()
            if chip.topology_id:
                try:
                    from qdash.common.topology_config import load_topology

                    self._topology = load_topology(chip.topology_id)
                except FileNotFoundError:
                    logger.warning(
                        f"Topology {chip.topology_id} not found, falling back to design-based"
                    )
        return self._topology

    def _get_topology_direction_set(self, inverse: bool = False) -> set[str] | None:
        """Get set of valid coupling directions from topology.

        Returns None if topology doesn't have checkerboard_cr convention.
        """
        topology = self._load_topology()
        if topology is None or topology.direction_convention != "checkerboard_cr":
            return None
        if inverse:
            return {f"{c[1]}-{c[0]}" for c in topology.couplings}
        else:
            return {f"{c[0]}-{c[1]}" for c in topology.couplings}

    def _load_wiring_config(self) -> list[dict[str, Any]]:
        """Load wiring configuration from YAML file."""
        if self._wiring_config is None:
            # Use provided path or default path
            if self.wiring_config_path is not None:
                wiring_path = Path(self.wiring_config_path)
            else:
                wiring_path = get_qubex_paths().wiring_yaml(self.chip_id)

            if not wiring_path.exists():
                msg = f"Wiring config not found: {wiring_path}"
                raise FileNotFoundError(msg)

            yaml_data = yaml.safe_load(wiring_path.read_text())
            self._wiring_config = yaml_data[self.chip_id]

        return self._wiring_config

    def _get_two_qubit_pair_list(self) -> list[str]:
        """Extract all two-qubit coupling IDs from CouplingDocument collection."""
        coupling_ids = self._load_coupling_ids()
        return [
            coupling_id
            for coupling_id in coupling_ids
            if "-" in coupling_id and len(coupling_id.split("-")) == 2
        ]

    def generate_with_plugins(
        self,
        filters: list[Any] | None = None,
        scheduler: Any | None = None,
    ) -> CRScheduleResult:
        """Generate CR schedule using pluggable filters and schedulers.

        This method provides a flexible plugin architecture for customizing
        the filtering and scheduling pipeline. Filters are applied sequentially,
        and the scheduler determines parallel grouping.

        Args:
            filters: List of CRPairFilter instances to apply in order.
                If None, uses default filters (frequency directionality only).
            scheduler: CRSchedulingStrategy instance for scheduling.
                If None, uses default (IntraThenInterMuxScheduler with MuxConflictScheduler).

        Returns:
            CRScheduleResult containing parallel_groups and metadata

        Raises:
            FileNotFoundError: If wiring configuration not found
            ValueError: If no valid CR pairs after filtering

        Example:
            ```python
            from qdash.workflow.engine.scheduler.plugins import (
                CandidateQubitFilter,
                FrequencyDirectionalityFilter,
                FidelityFilter,
                IntraThenInterMuxScheduler,
                MuxConflictScheduler,
            )

            # Custom filter pipeline
            filters = [
                CandidateQubitFilter(["0", "1", "2", "3"]),
                FrequencyDirectionalityFilter(use_design_based=True),
                FidelityFilter(min_fidelity=0.95),
            ]

            # Custom scheduler
            scheduler = IntraThenInterMuxScheduler(
                inner_scheduler=MuxConflictScheduler(
                    max_parallel_ops=10,
                    coloring_strategy="saturation_largest_first"
                )
            )

            cr_scheduler = CRScheduler(username="alice", chip_id="64Qv3")
            schedule = cr_scheduler.generate_with_plugins(filters=filters, scheduler=scheduler)
            ```
        """
        from qdash.workflow.engine.scheduler.plugins import (
            FilterContext,
            FrequencyDirectionalityFilter,
            IntraThenInterMuxScheduler,
            MuxConflictScheduler,
            ScheduleContext,
        )

        logger.info(
            f"Generating CR schedule (plugin mode) for chip_id={self.chip_id}, username={self.username}"
        )

        # Load chip metadata and qubit data from individual documents (scalable)
        chip = self._load_chip_data()
        qubit_models = self._load_qubit_models()
        qubit_frequency = extract_qubit_frequency(qubit_models)

        # Load MUX configuration
        wiring_config = self._load_wiring_config()
        mux_conflict_map = build_mux_conflict_map(wiring_config)
        qid_to_mux = build_qubit_to_mux_map(wiring_config)

        # Determine grid size
        grid_size = 12 if "144Q" in self.chip_id else 8

        # Load topology directions if available
        topology_directions = self._get_topology_direction_set(inverse=False)

        # Create filter context with qubit models for scalable filtering
        filter_context = FilterContext(
            chip=chip,
            grid_size=grid_size,
            qubit_frequency=qubit_frequency,
            qid_to_mux=qid_to_mux,
            qubit_models=qubit_models,
            topology_directions=topology_directions,
        )

        # Use default filters if not provided
        if filters is None:
            # Auto-select frequency directionality method
            use_design_based = len(qubit_frequency) == 0
            filters = [
                FrequencyDirectionalityFilter(use_design_based=use_design_based),
            ]

        # Get all coupling pairs from individual documents
        all_pairs = self._get_two_qubit_pair_list()
        logger.info(f"Starting with {len(all_pairs)} coupling pairs")

        # Apply filters sequentially
        filtered_pairs = all_pairs
        filter_stats = []
        for i, filter_obj in enumerate(filters, 1):
            filtered_pairs = filter_obj.filter(filtered_pairs, filter_context)
            stats = filter_obj.get_stats()
            filter_stats.append(stats)
            logger.info(
                f"  Filter {i} ({stats['filter_name']}): {stats['input_pairs']} → {stats['output_pairs']}"
            )

        if len(filtered_pairs) == 0:
            msg = "No valid CR pairs after filtering"
            logger.error(msg)
            raise ValueError(msg)

        # Use default scheduler if not provided
        if scheduler is None:
            scheduler = IntraThenInterMuxScheduler(
                inner_scheduler=MuxConflictScheduler(
                    max_parallel_ops=10, coloring_strategy="largest_first"
                )
            )

        # Create schedule context
        schedule_context = ScheduleContext(
            qid_to_mux=qid_to_mux,
            mux_conflict_map=mux_conflict_map,
        )

        # Apply scheduler
        grouped = scheduler.schedule(filtered_pairs, schedule_context)
        scheduler_metadata = scheduler.get_metadata()

        # Convert to parallel_groups format
        parallel_groups = convert_to_parallel_groups(grouped)

        # Calculate fast/slow split for metadata
        fast, slow = split_fast_slow_pairs(filtered_pairs, qid_to_mux)

        logger.info(
            f"Generated schedule: {sum(len(g) for g in parallel_groups)} pairs in {len(parallel_groups)} groups"
        )
        logger.info(f"  Fast pairs (intra-MUX): {len(fast)}, Slow pairs (inter-MUX): {len(slow)}")

        # Build result metadata
        metadata = {
            "total_pairs": len(filtered_pairs),
            "scheduled_pairs": sum(len(g) for g in parallel_groups),
            "fast_pairs": len(fast),
            "slow_pairs": len(slow),
            "num_groups": len(parallel_groups),
            "grid_size": grid_size,
            "scheduler": scheduler_metadata,
            "filters": [repr(f) for f in filters],
        }

        filtering_stats = {
            "all_coupling_pairs": len(all_pairs),
            "final_filtered_pairs": len(filtered_pairs),
            "filter_pipeline": filter_stats,
        }

        return CRScheduleResult(
            parallel_groups=parallel_groups,
            metadata=metadata,
            filtering_stats=filtering_stats,
            cr_pairs_string=filtered_pairs,
            qid_to_mux=qid_to_mux,
            mux_conflict_map=mux_conflict_map,
        )

    def generate(
        self,
        candidate_qubits: list[str] | None = None,
        max_parallel_ops: int = 10,
        coloring_strategy: str = "largest_first",
        inverse: bool = False,
    ) -> CRScheduleResult:
        """Generate CR execution schedule.

        Args:
            candidate_qubits: List of qubit IDs that are candidates for CR calibration.
                These should be qubits that passed Stage 1 calibration with sufficient quality.
                If None, uses all qubits from chip document.
            max_parallel_ops: Maximum parallel operations per step (default: 10)
            coloring_strategy: Graph coloring strategy for parallel grouping (default: "largest_first").
                Options:
                - "largest_first": Largest degree first (good general performance)
                - "smallest_last": Smallest degree last (often better quality)
                - "saturation_largest_first": DSATUR algorithm (often optimal, may be slower)
                - "random_sequential": Random order (non-deterministic)
                - "connected_sequential_bfs": BFS ordering
                - "connected_sequential_dfs": DFS ordering
            inverse: If True, select reverse-direction pairs (target→control).
                Only fully supported with topology-based direction. For measured
                directionality, inverts the frequency comparison.

        Returns:
            CRScheduleResult containing parallel_groups and metadata

        Raises:
            FileNotFoundError: If wiring configuration not found
            ValueError: If no valid CR pairs after filtering

        Example:
            ```python
            # Use all qubits from chip document
            scheduler = CRScheduler("alice", "64Qv3")
            schedule = scheduler.generate()

            # Use only high-quality qubits from Stage 1
            high_quality_qubits = ["0", "1", "2", "3"]  # From stage1 calibration
            schedule = scheduler.generate(candidate_qubits=high_quality_qubits)

            # Generate inverse direction schedule
            schedule = scheduler.generate(inverse=True)

            # Use different coloring strategy for potentially better parallelization
            schedule = scheduler.generate(
                candidate_qubits=high_quality_qubits,
                coloring_strategy="saturation_largest_first"
            )
            print(f"Generated {len(schedule.parallel_groups)} groups")
            ```

        """
        logger.info(f"Generating CR schedule for chip_id={self.chip_id}, username={self.username}")
        logger.info(f"  max_parallel_ops={max_parallel_ops}, inverse={inverse}")
        if candidate_qubits is not None:
            logger.info(
                f"  Using {len(candidate_qubits)} candidate qubits from stage1: {candidate_qubits}"
            )

        # Load qubit data from individual documents (scalable)
        qubit_models = self._load_qubit_models()
        qubit_frequency = extract_qubit_frequency(qubit_models)

        logger.debug(f"  Total qubits in chip: {len(qubit_models)}")
        logger.debug(f"  Qubits with frequency data: {len(qubit_frequency)}")

        # Get all coupling pairs from individual documents
        all_pairs = self._get_two_qubit_pair_list()

        # Determine grid size from chip_id
        grid_size = 12 if "144Q" in self.chip_id else 8

        # Filter by candidate qubits if provided
        if candidate_qubits is not None:
            candidate_set = set(candidate_qubits)
            all_pairs = [
                pair
                for pair in all_pairs
                if (qubits := pair.split("-"))
                and len(qubits) == 2
                and qubits[0] in candidate_set
                and qubits[1] in candidate_set
            ]
            logger.info(
                f"Filtered to {len(all_pairs)} pairs using {len(candidate_qubits)} candidate qubits"
            )

        # Filter by frequency directionality
        # Priority: topology-based > design-based > measured
        topology_directions = self._get_topology_direction_set(inverse=inverse)
        use_design_based = len(qubit_frequency) == 0

        if topology_directions is not None:
            direction_method = "topology"
            logger.info(f"Using topology-based direction (inverse={inverse})")
            cr_pairs = [p for p in all_pairs if p in topology_directions]
        elif use_design_based:
            direction_method = "design_based"
            logger.info(
                f"Using design-based frequency directionality (checkerboard pattern, inverse={inverse})"
            )
            if inverse:
                cr_pairs = [
                    pair
                    for pair in all_pairs
                    if (qubits := pair.split("-"))
                    and len(qubits) == 2
                    and not infer_direction_from_design(qubits[0], qubits[1], grid_size)
                ]
            else:
                cr_pairs = [
                    pair
                    for pair in all_pairs
                    if (qubits := pair.split("-"))
                    and len(qubits) == 2
                    and infer_direction_from_design(qubits[0], qubits[1], grid_size)
                ]
        else:
            direction_method = "measured"
            logger.info("Using measured frequency directionality")
            if inverse:
                cr_pairs = [
                    pair
                    for pair in all_pairs
                    if (qubits := pair.split("-"))
                    and len(qubits) == 2
                    and qubits[0] in qubit_frequency
                    and qubits[1] in qubit_frequency
                    and qubit_frequency[qubits[0]] > qubit_frequency[qubits[1]]
                ]
            else:
                cr_pairs = [
                    pair
                    for pair in all_pairs
                    if (qubits := pair.split("-"))
                    and len(qubits) == 2
                    and qubits[0] in qubit_frequency
                    and qubits[1] in qubit_frequency
                    and qubit_frequency[qubits[0]] < qubit_frequency[qubits[1]]
                ]

        logger.info(f"Filtering: {len(all_pairs)} total → {len(cr_pairs)} with freq directionality")

        if len(cr_pairs) == 0:
            msg = "No valid CR pairs after filtering"
            logger.error(msg)
            raise ValueError(msg)

        # Load MUX configuration
        wiring_config = self._load_wiring_config()
        mux_conflict_map = build_mux_conflict_map(wiring_config)
        qid_to_mux = build_qubit_to_mux_map(wiring_config)

        # Filter out CR pairs that have qubits without MUX mappings
        pairs_before_mux_filter = len(cr_pairs)
        cr_pairs = [pair for pair in cr_pairs if all(qid in qid_to_mux for qid in pair.split("-"))]
        if pairs_before_mux_filter != len(cr_pairs):
            logger.warning(
                f"Filtered out {pairs_before_mux_filter - len(cr_pairs)} pairs "
                f"with qubits missing from MUX configuration"
            )

        if len(cr_pairs) == 0:
            msg = "No valid CR pairs after MUX configuration filtering"
            logger.error(msg)
            raise ValueError(msg)

        # Group pairs: fast (intra-MUX) first, then slow (inter-MUX)
        fast, slow = split_fast_slow_pairs(cr_pairs, qid_to_mux)
        grouped = group_cr_pairs_by_conflict(
            fast, qid_to_mux, mux_conflict_map, max_parallel_ops, coloring_strategy
        ) + group_cr_pairs_by_conflict(
            slow, qid_to_mux, mux_conflict_map, max_parallel_ops, coloring_strategy
        )

        # Convert to parallel_groups format
        parallel_groups = convert_to_parallel_groups(grouped)

        logger.info(
            f"Generated schedule: {sum(len(g) for g in parallel_groups)} pairs in {len(parallel_groups)} groups"
        )
        logger.info(f"  Fast pairs (intra-MUX): {len(fast)}, Slow pairs (inter-MUX): {len(slow)}")

        # Build result
        metadata = {
            "total_pairs": len(cr_pairs),
            "scheduled_pairs": sum(len(g) for g in parallel_groups),
            "fast_pairs": len(fast),
            "slow_pairs": len(slow),
            "num_groups": len(parallel_groups),
            "max_parallel_ops": max_parallel_ops,
            "coloring_strategy": coloring_strategy,
            "candidate_qubits_count": len(candidate_qubits)
            if candidate_qubits is not None
            else None,
            "direction_method": direction_method,
            "inverse": inverse,
            "grid_size": grid_size,
        }

        filtering_stats = {
            "all_coupling_pairs": len(all_pairs),
            "freq_directionality_filtered": pairs_before_mux_filter,
            "mux_config_filtered": len(cr_pairs),
            "mux_filtered_out": pairs_before_mux_filter - len(cr_pairs),
            "used_candidate_qubits": candidate_qubits is not None,
            "direction_method": direction_method,
            "inverse": inverse,
        }

        return CRScheduleResult(
            parallel_groups=parallel_groups,
            metadata=metadata,
            filtering_stats=filtering_stats,
            cr_pairs_string=cr_pairs,
            qid_to_mux=qid_to_mux,
            mux_conflict_map=mux_conflict_map,
        )
