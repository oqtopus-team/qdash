"""CR Gate Schedule Generator for Workflow Engine.

This module provides a clean API for generating optimized CR gate execution schedules
based on hardware constraints, qubit quality metrics, and MUX resource conflicts.

Example:
    Basic usage in a calibration flow:

    ```python
    from qdash.workflow.engine.calibration.cr_scheduler import CRScheduler

    scheduler = CRScheduler(username, chip_id)
    schedule = scheduler.generate(min_x90_fidelity=0.95, max_parallel_ops=10)

    # Use the schedule
    parallel_groups = schedule["parallel_groups"]  # [[(c, t), ...], ...]
    for group in parallel_groups:
        # Execute group in parallel
        pass
    ```
"""

import itertools
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
import yaml
from qdash.datamodel.qubit import QubitModel
from qdash.dbmodel.chip import ChipDocument

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
        filtering_stats: dict[str, int],
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
    - X90 gate fidelity filtering
    - Frequency directionality constraints
    - MUX resource conflict detection
    - Greedy graph coloring for parallel grouping

    Example:
        ```python
        # Use default wiring config path
        scheduler = CRScheduler(username="alice", chip_id="64Qv3")
        schedule = scheduler.generate()

        # Or specify custom wiring config path
        scheduler = CRScheduler(
            username="alice",
            chip_id="64Qv3",
            wiring_config_path="/custom/path/to/wiring.yaml"
        )
        schedule = scheduler.generate()

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
    ) -> None:
        """Initialize CR scheduler.

        Args:
            username: Username for chip data access
            chip_id: Chip ID
            wiring_config_path: Path to wiring.yaml configuration file.
                If None, uses default path: /workspace/qdash/config/qubex/{chip_id}/config/wiring.yaml

        """
        self.username = username
        self.chip_id = chip_id
        self.wiring_config_path = wiring_config_path
        self._chip_doc: ChipDocument | None = None
        self._wiring_config: dict[str, Any] | None = None

    def _load_chip_data(self) -> ChipDocument:
        """Load chip document from database."""
        if self._chip_doc is None:
            self._chip_doc = ChipDocument.get_current_chip(self.username)
        return self._chip_doc

    def _load_wiring_config(self) -> dict[str, Any]:
        """Load wiring configuration from YAML file."""
        if self._wiring_config is None:
            # Use provided path or default path
            if self.wiring_config_path is not None:
                wiring_path = Path(self.wiring_config_path)
            else:
                wiring_path = Path(f"/workspace/qdash/config/qubex/{self.chip_id}/config/wiring.yaml")

            if not wiring_path.exists():
                msg = f"Wiring config not found: {wiring_path}"
                raise FileNotFoundError(msg)

            yaml_data = yaml.safe_load(wiring_path.read_text())
            self._wiring_config = yaml_data[self.chip_id]

        return self._wiring_config

    @staticmethod
    def _extract_qubit_frequency(qubits: dict[str, QubitModel]) -> dict[str, float]:
        """Extract qubit frequencies from chip data."""
        return {
            qid: qubit.data["qubit_frequency"]["value"]
            for qid, qubit in qubits.items()
            if qubit.data and "qubit_frequency" in qubit.data
        }

    @staticmethod
    def _get_two_qubit_pair_list(chip_doc: ChipDocument) -> list[str]:
        """Extract all two-qubit coupling IDs from chip document."""
        return [
            coupling_id
            for coupling_id in chip_doc.couplings.keys()
            if "-" in coupling_id and len(coupling_id.split("-")) == 2
        ]

    @staticmethod
    def _build_mux_conflict_map(yaml_mux_list: list[dict[str, Any]]) -> dict[int, set[int]]:
        """Build conflict map for MUX resources.

        MUXes conflict if they share the same readout or control module.
        """
        module_to_muxes_readout: dict[str, set[int]] = defaultdict(set)
        module_to_muxes_ctrl: dict[str, set[int]] = defaultdict(set)

        # Group MUXes by readout and control modules
        for mux_entry in yaml_mux_list:
            mux_id = mux_entry["mux"]

            # Readout module conflicts
            read_out = mux_entry.get("read_out")
            if read_out:
                readout_module = read_out.split("-")[0]
                module_to_muxes_readout[readout_module].add(mux_id)

            # Control module conflicts
            for ctrl in mux_entry.get("ctrl", []):
                ctrl_module = ctrl.split("-")[0]
                module_to_muxes_ctrl[ctrl_module].add(mux_id)

        def create_conflict_map(module_to_muxes: dict[str, set[int]]) -> dict[int, set[int]]:
            """Create bidirectional conflict map from module groupings."""
            mux_conflict: dict[int, set[int]] = defaultdict(set)
            for muxes in module_to_muxes.values():
                for mux_a, mux_b in itertools.combinations(muxes, 2):
                    mux_conflict[mux_a].add(mux_b)
                    mux_conflict[mux_b].add(mux_a)
            return mux_conflict

        # Merge readout and control conflicts
        conflict_map = create_conflict_map(module_to_muxes_readout)
        ctrl_conflict_map = create_conflict_map(module_to_muxes_ctrl)

        for mux_id, conflicts in ctrl_conflict_map.items():
            conflict_map[mux_id].update(conflicts)

        return dict(conflict_map)

    @staticmethod
    def _build_qubit_to_mux_map(yaml_mux_list: list[dict[str, Any]]) -> dict[str, int]:
        """Build mapping from qubit ID to MUX ID.

        Each MUX controls 4 qubits: MUX_N controls qubits [4N, 4N+1, 4N+2, 4N+3].
        """
        qid_to_mux = {}
        for entry in yaml_mux_list:
            mux_id = entry["mux"]
            for offset in range(4):
                qid_to_mux[str(mux_id * 4 + offset)] = mux_id
        return qid_to_mux

    @staticmethod
    def _group_cr_pairs_by_conflict(
        cr_pairs: list[str],
        qid_to_mux: dict[str, int],
        mux_conflict_map: dict[int, set[int]],
        max_parallel_ops: int | None = None,
        coloring_strategy: str = "largest_first",
    ) -> list[list[str]]:
        """Group CR pairs into parallel execution steps using greedy graph coloring.

        Args:
            cr_pairs: List of CR pair strings (e.g., ["0-1", "2-3"])
            qid_to_mux: Mapping from qubit ID to MUX ID
            mux_conflict_map: MUX conflict relationships
            max_parallel_ops: Maximum parallel operations per group
            coloring_strategy: NetworkX graph coloring strategy. Options:
                - "largest_first": Largest degree first (default, good general performance)
                - "smallest_last": Smallest degree last (often better quality)
                - "random_sequential": Random order (non-deterministic)
                - "connected_sequential_bfs": BFS ordering
                - "connected_sequential_dfs": DFS ordering
                - "saturation_largest_first": DSATUR algorithm (often optimal)

        Returns:
            List of groups where each group contains CR pairs that can run in parallel
        """
        # Build conflict graph
        conflict_graph = nx.Graph()
        conflict_graph.add_nodes_from(cr_pairs)

        for pair_a, pair_b in itertools.combinations(cr_pairs, 2):
            q1a, q2a = pair_a.split("-")
            q1b, q2b = pair_b.split("-")

            # Conflict 1: Shared qubits
            if set([q1a, q2a]) & set([q1b, q2b]):
                conflict_graph.add_edge(pair_a, pair_b)
                continue

            # Conflict 2: Same MUX usage
            mux_a1, mux_a2 = qid_to_mux[q1a], qid_to_mux[q2a]
            mux_b1, mux_b2 = qid_to_mux[q1b], qid_to_mux[q2b]

            if mux_a1 in (mux_b1, mux_b2) or mux_a2 in (mux_b1, mux_b2):
                conflict_graph.add_edge(pair_a, pair_b)
                continue

            # Conflict 3: MUX resource conflicts
            conflict_muxes = mux_conflict_map.get(mux_a1, set()) | mux_conflict_map.get(mux_a2, set())
            if mux_b1 in conflict_muxes or mux_b2 in conflict_muxes:
                conflict_graph.add_edge(pair_a, pair_b)

        # Greedy graph coloring
        coloring = nx.coloring.greedy_color(conflict_graph, strategy=coloring_strategy)

        # Group pairs by color
        color_groups: dict[int, list[str]] = defaultdict(list)
        for pair, color in coloring.items():
            color_groups[color].append(pair)

        # Convert to sorted list of groups
        groups = [color_groups[c] for c in sorted(color_groups)]

        # Optionally split groups that exceed max parallel operations limit
        if max_parallel_ops is not None:
            split_groups = []
            for group in groups:
                for i in range(0, len(group), max_parallel_ops):
                    chunk = group[i : i + max_parallel_ops]
                    split_groups.append(chunk)
            return split_groups

        return groups

    @staticmethod
    def _split_fast_slow_pairs(cr_pairs: list[str], qid_to_mux: dict[str, int]) -> tuple[list[str], list[str]]:
        """Separate CR pairs into fast (intra-MUX) and slow (inter-MUX) categories."""
        fast_pairs = [p for p in cr_pairs if qid_to_mux.get(p.split("-")[0]) == qid_to_mux.get(p.split("-")[1])]
        slow_pairs = [p for p in cr_pairs if qid_to_mux.get(p.split("-")[0]) != qid_to_mux.get(p.split("-")[1])]
        return fast_pairs, slow_pairs

    @staticmethod
    def _convert_to_parallel_groups(grouped: list[list[str]]) -> list[list[tuple[str, str]]]:
        """Convert grouped CR pairs to parallel_groups format."""
        return [[tuple(pair.split("-")) for pair in group] for group in grouped]

    def generate(
        self,
        candidate_qubits: list[str] | None = None,
        max_parallel_ops: int = 10,
        coloring_strategy: str = "largest_first",
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

            # Use different coloring strategy for potentially better parallelization
            schedule = scheduler.generate(
                candidate_qubits=high_quality_qubits,
                coloring_strategy="saturation_largest_first"
            )
            print(f"Generated {len(schedule.parallel_groups)} groups")
            ```

        """
        logger.info(f"Generating CR schedule for chip_id={self.chip_id}, username={self.username}")
        logger.info(f"  max_parallel_ops={max_parallel_ops}")
        if candidate_qubits is not None:
            logger.info(f"  Using {len(candidate_qubits)} candidate qubits from stage1: {candidate_qubits}")

        # Load chip data
        chip_doc = self._load_chip_data()
        qubit_frequency = self._extract_qubit_frequency(chip_doc.qubits)

        logger.debug(f"  Total qubits in chip: {len(chip_doc.qubits)}")
        logger.debug(f"  Qubits with frequency data: {len(qubit_frequency)}")

        # Get all coupling pairs
        all_pairs = self._get_two_qubit_pair_list(chip_doc)

        # Check if we have required data
        if len(qubit_frequency) == 0:
            msg = "No qubit frequency data found. Please run qubit frequency calibration first."
            logger.error(msg)
            raise ValueError(msg)

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
            logger.info(f"Filtered to {len(all_pairs)} pairs using {len(candidate_qubits)} candidate qubits")

        # Filter by frequency directionality
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
        mux_conflict_map = self._build_mux_conflict_map(wiring_config)
        qid_to_mux = self._build_qubit_to_mux_map(wiring_config)

        # Group pairs: fast (intra-MUX) first, then slow (inter-MUX)
        fast, slow = self._split_fast_slow_pairs(cr_pairs, qid_to_mux)
        grouped = self._group_cr_pairs_by_conflict(
            fast, qid_to_mux, mux_conflict_map, max_parallel_ops, coloring_strategy
        ) + self._group_cr_pairs_by_conflict(slow, qid_to_mux, mux_conflict_map, max_parallel_ops, coloring_strategy)

        # Convert to parallel_groups format
        parallel_groups = self._convert_to_parallel_groups(grouped)

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
            "candidate_qubits_count": len(candidate_qubits) if candidate_qubits is not None else None,
        }

        filtering_stats = {
            "all_coupling_pairs": len(all_pairs),
            "freq_directionality_filtered": len(cr_pairs),
            "used_candidate_qubits": candidate_qubits is not None,
        }

        return CRScheduleResult(
            parallel_groups=parallel_groups,
            metadata=metadata,
            filtering_stats=filtering_stats,
            cr_pairs_string=cr_pairs,
            qid_to_mux=qid_to_mux,
            mux_conflict_map=mux_conflict_map,
        )
