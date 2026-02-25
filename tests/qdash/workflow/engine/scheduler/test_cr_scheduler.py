"""Tests for CR Scheduler.

These tests verify the CRScheduler functionality including:
- MUX conflict detection
- Frequency directionality filtering
- Graph coloring strategies
- Parallel grouping
- Topology-based direction filtering
- Inverse direction support
"""

from unittest.mock import MagicMock, patch

import pytest
from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler, CRScheduleResult
from qdash.workflow.engine.scheduler.cr_utils import (
    build_mux_conflict_map,
    build_qubit_to_mux_map,
    extract_qubit_frequency,
    group_cr_pairs_by_conflict,
    infer_direction_from_design,
    qid_to_coords,
    split_fast_slow_pairs,
)


@pytest.fixture
def mock_chip():
    """Mock ChipModel with metadata only (no embedded qubits/couplings)."""
    chip = MagicMock()
    chip.project_id = "test_project"
    chip.chip_id = "test_chip"
    chip.size = 64
    return chip


@pytest.fixture
def mock_qubit_models():
    """Mock qubit models from individual QubitDocument collection."""
    return {
        "0": MagicMock(data={"qubit_frequency": {"value": 5.0}}),
        "1": MagicMock(data={"qubit_frequency": {"value": 5.1}}),
        "2": MagicMock(data={"qubit_frequency": {"value": 5.2}}),
        "3": MagicMock(data={"qubit_frequency": {"value": 5.3}}),
        "4": MagicMock(data={"qubit_frequency": {"value": 5.4}}),
        "5": MagicMock(data={"qubit_frequency": {"value": 5.5}}),
    }


@pytest.fixture
def mock_coupling_ids():
    """Mock coupling IDs from individual CouplingDocument collection."""
    return ["0-1", "1-2", "2-3", "3-4", "4-5", "0-4"]


@pytest.fixture
def mock_wiring_config():
    """Mock wiring configuration with MUX setup."""
    return [
        {
            "mux": 0,
            "read_out": "READOUT-0",
            "ctrl": ["CTRL-0", "CTRL-1"],
        },
        {
            "mux": 1,
            "read_out": "READOUT-0",  # Same readout as MUX 0 (conflict)
            "ctrl": ["CTRL-2", "CTRL-3"],
        },
        {
            "mux": 2,
            "read_out": "READOUT-1",
            "ctrl": ["CTRL-4", "CTRL-5"],
        },
    ]


@pytest.fixture
def scheduler(tmp_path, mock_chip, mock_qubit_models, mock_wiring_config):
    """Create CRScheduler instance with mocked dependencies."""
    # Create temporary wiring.yaml
    wiring_file = tmp_path / "wiring.yaml"
    import yaml

    wiring_file.write_text(yaml.dump({"test_chip": mock_wiring_config}))

    scheduler = CRScheduler(
        username="test_user", chip_id="test_chip", wiring_config_path=str(wiring_file)
    )

    # Mock chip data loading (now returns ChipModel without embedded data)
    scheduler._chip = mock_chip
    scheduler._qubit_models = mock_qubit_models

    return scheduler


# Initialization tests
def test_scheduler_initialization():
    """Test that CRScheduler initializes with correct parameters."""
    scheduler = CRScheduler(
        username="alice", chip_id="64Qv3", wiring_config_path="/custom/path/wiring.yaml"
    )

    assert scheduler.username == "alice"
    assert scheduler.chip_id == "64Qv3"
    assert scheduler.wiring_config_path == "/custom/path/wiring.yaml"


def test_scheduler_default_wiring_path():
    """Test that default wiring path is used when not specified."""
    scheduler = CRScheduler(username="alice", chip_id="64Qv3")

    assert scheduler.username == "alice"
    assert scheduler.chip_id == "64Qv3"
    assert scheduler.wiring_config_path is None


# MUX conflict detection tests
def test_build_mux_conflict_map(mock_wiring_config):
    """Test MUX conflict map construction."""
    conflict_map = build_mux_conflict_map(mock_wiring_config)

    # MUX 0 and MUX 1 should conflict (same readout module)
    assert 1 in conflict_map[0]
    assert 0 in conflict_map[1]

    # All MUXes conflict with each other due to shared readout/control modules
    assert len(conflict_map) > 0


def test_build_qubit_to_mux_map(mock_wiring_config):
    """Test qubit-to-MUX mapping."""
    qid_to_mux = build_qubit_to_mux_map(mock_wiring_config)

    # MUX 0 controls qubits 0-3
    assert qid_to_mux["0"] == 0
    assert qid_to_mux["1"] == 0
    assert qid_to_mux["2"] == 0
    assert qid_to_mux["3"] == 0

    # MUX 1 controls qubits 4-7
    assert qid_to_mux["4"] == 1
    assert qid_to_mux["5"] == 1


# Coordinate conversion tests
def test_qid_to_coords():
    """Test qubit ID to coordinate conversion."""
    # 64-qubit chip (8x8 grid)
    assert qid_to_coords(0, 8) == (0, 0)  # MUX 0, TL
    assert qid_to_coords(1, 8) == (0, 1)  # MUX 0, TR
    assert qid_to_coords(2, 8) == (1, 0)  # MUX 0, BL
    assert qid_to_coords(3, 8) == (1, 1)  # MUX 0, BR
    assert qid_to_coords(4, 8) == (0, 2)  # MUX 1, TL
    assert qid_to_coords(16, 8) == (2, 0)  # MUX 4, TL

    # 144-qubit chip (12x12 grid)
    assert qid_to_coords(0, 12) == (0, 0)
    assert qid_to_coords(1, 12) == (0, 1)


def test_infer_direction_from_design():
    """Test design-based CR direction inference using checkerboard pattern."""
    # 64-qubit chip (8x8 grid)
    # Qubit 0: (0,0) → sum=0 (even) → low freq
    # Qubit 1: (0,1) → sum=1 (odd) → high freq
    assert infer_direction_from_design("0", "1", 8) is True  # 0→1 valid (low→high)

    # Qubit 0: (0,0) → sum=0 (even) → low freq
    # Qubit 2: (1,0) → sum=1 (odd) → high freq
    assert infer_direction_from_design("0", "2", 8) is True  # 0→2 valid (low→high)

    # Qubit 1: (0,1) → sum=1 (odd) → high freq
    # Qubit 0: (0,0) → sum=0 (even) → low freq
    assert infer_direction_from_design("1", "0", 8) is False  # 1→0 invalid (high→low)

    # Qubit 2: (1,0) → sum=1 (odd) → high freq
    # Qubit 3: (1,1) → sum=2 (even) → low freq
    assert infer_direction_from_design("2", "3", 8) is False  # 2→3 invalid (high→low)


# Frequency filtering tests
def test_extract_qubit_frequency(mock_qubit_models):
    """Test frequency extraction from qubit models."""
    frequencies = extract_qubit_frequency(mock_qubit_models)

    assert frequencies["0"] == 5.0
    assert frequencies["1"] == 5.1
    assert len(frequencies) == 6


def test_frequency_directionality_filter(scheduler):
    """Test that only lower->higher frequency pairs are kept."""
    all_pairs = ["0-1", "1-0", "1-2", "2-1"]

    # Load frequency data from qubit models
    frequencies = extract_qubit_frequency(scheduler._qubit_models)

    # Filter by frequency directionality (control < target)
    filtered = [
        pair
        for pair in all_pairs
        if (qubits := pair.split("-")) and frequencies[qubits[0]] < frequencies[qubits[1]]
    ]

    # Only 0-1 and 1-2 should pass (lower -> higher)
    assert "0-1" in filtered
    assert "1-2" in filtered
    assert "1-0" not in filtered
    assert "2-1" not in filtered


# Candidate qubit filtering tests
def test_candidate_qubit_filter(scheduler):
    """Test that only pairs with candidate qubits are kept."""
    all_pairs = ["0-1", "1-2", "2-3", "3-4", "4-5"]
    candidate_qubits = ["0", "1", "2"]

    candidate_set = set(candidate_qubits)
    filtered = [
        pair
        for pair in all_pairs
        if (qubits := pair.split("-")) and qubits[0] in candidate_set and qubits[1] in candidate_set
    ]

    # Only pairs within candidate set should remain
    assert "0-1" in filtered
    assert "1-2" in filtered
    assert "2-3" not in filtered  # 3 not in candidates
    assert "4-5" not in filtered  # Neither in candidates


# Graph coloring tests
@pytest.mark.parametrize(
    "cr_pairs,qid_to_mux,expected_min_groups,reason",
    [
        (["0-1", "2-3"], {"0": 0, "1": 0, "2": 0, "3": 0}, 2, "same MUX conflict"),
        (["0-1", "1-2"], {"0": 0, "1": 0, "2": 0}, 2, "shared qubit conflict"),
        (["0-1", "4-5"], {"0": 0, "1": 0, "4": 1, "5": 1}, 1, "different MUX, no conflicts"),
    ],
)
def test_group_cr_pairs_by_conflict(cr_pairs, qid_to_mux, expected_min_groups, reason):
    """Test CR pair grouping with various conflict scenarios."""
    mux_conflict_map: dict[int, set[int]] = {}

    groups = group_cr_pairs_by_conflict(cr_pairs, qid_to_mux, mux_conflict_map)

    assert len(groups) >= expected_min_groups, f"Failed: {reason}"

    # Verify no conflicts within groups
    for group in groups:
        qubits_in_group = set()
        for pair in group:
            q1, q2 = pair.split("-")
            assert q1 not in qubits_in_group
            assert q2 not in qubits_in_group
            qubits_in_group.add(q1)
            qubits_in_group.add(q2)


@pytest.mark.parametrize(
    "strategy",
    [
        "largest_first",
        "smallest_last",
        "saturation_largest_first",
    ],
)
def test_coloring_strategies(strategy):
    """Test different coloring strategies produce valid results."""
    cr_pairs = ["0-1", "1-2", "2-3"]
    qid_to_mux = {"0": 0, "1": 0, "2": 0, "3": 0}
    mux_conflict_map: dict[int, set[int]] = {}

    groups = group_cr_pairs_by_conflict(
        cr_pairs, qid_to_mux, mux_conflict_map, coloring_strategy=strategy
    )

    # All strategies should produce valid grouping
    assert len(groups) >= 2

    # Verify no conflicts within groups
    for group in groups:
        qubits_in_group = set()
        for pair in group:
            q1, q2 = pair.split("-")
            assert q1 not in qubits_in_group and q2 not in qubits_in_group
            qubits_in_group.update([q1, q2])


# Schedule generation tests
@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_with_design_based_direction(mock_load, mock_qubits, mock_couplings, scheduler):
    """Test schedule generation using design-based direction inference."""
    # Create chip without frequency data to trigger design-based inference
    chip = MagicMock()
    chip.project_id = "test_project"
    chip.size = 64
    mock_load.return_value = chip

    # Qubit models without frequency data
    mock_qubits.return_value = {
        "0": MagicMock(data=None),
        "1": MagicMock(data=None),
        "2": MagicMock(data=None),
        "3": MagicMock(data=None),
    }

    # Coupling IDs
    mock_couplings.return_value = ["0-1", "1-2", "2-3"]

    schedule = scheduler.generate(candidate_qubits=["0", "1", "2", "3"])

    # Check that design-based method was used
    assert schedule.metadata["direction_method"] == "design_based"
    assert schedule.filtering_stats["direction_method"] == "design_based"

    # Check that correct pairs were selected based on design pattern
    all_pairs = [pair for group in schedule.parallel_groups for pair in group]
    # 0-1: (0,0)→(0,1) even→odd ✓
    # 1-2: (0,1)→(1,0) odd→odd ✗
    # 2-3: (1,0)→(1,1) odd→even ✗
    assert ("0", "1") in all_pairs
    assert ("1", "2") not in all_pairs
    assert ("2", "3") not in all_pairs


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_with_measured_direction(
    mock_load,
    mock_qubits,
    mock_couplings,
    scheduler,
    mock_chip,
    mock_qubit_models,
    mock_coupling_ids,
):
    """Test schedule generation using measured frequency directionality."""
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    mock_couplings.return_value = mock_coupling_ids

    schedule = scheduler.generate(candidate_qubits=["0", "1", "2", "3"])

    # Check that measured method was used
    assert schedule.metadata["direction_method"] == "measured"
    assert schedule.filtering_stats["direction_method"] == "measured"


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_full_schedule(
    mock_load,
    mock_qubits,
    mock_couplings,
    scheduler,
    mock_chip,
    mock_qubit_models,
    mock_coupling_ids,
):
    """Test complete schedule generation."""
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    mock_couplings.return_value = mock_coupling_ids

    schedule = scheduler.generate(
        candidate_qubits=["0", "1", "2", "3"],
        max_parallel_ops=10,
        coloring_strategy="largest_first",
    )

    assert isinstance(schedule, CRScheduleResult)
    assert len(schedule.parallel_groups) > 0
    assert schedule.metadata["coloring_strategy"] == "largest_first"
    assert schedule.metadata["candidate_qubits_count"] == 4


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_with_max_parallel_ops(
    mock_load,
    mock_qubits,
    mock_couplings,
    scheduler,
    mock_chip,
    mock_qubit_models,
    mock_coupling_ids,
):
    """Test schedule generation with parallel operation limit."""
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    mock_couplings.return_value = mock_coupling_ids

    schedule = scheduler.generate(
        candidate_qubits=["0", "1", "2", "3", "4", "5"], max_parallel_ops=2
    )

    # Each group should have at most 2 pairs
    for group in schedule.parallel_groups:
        assert len(group) <= 2


# Fast/slow pair splitting tests
def test_split_fast_slow_pairs():
    """Test splitting into intra-MUX and inter-MUX pairs."""
    cr_pairs = ["0-1", "0-4", "4-5"]  # 0-1 intra, 0-4 inter, 4-5 intra
    qid_to_mux = {"0": 0, "1": 0, "4": 1, "5": 1}

    fast, slow = split_fast_slow_pairs(cr_pairs, qid_to_mux)

    assert "0-1" in fast  # Same MUX
    assert "4-5" in fast  # Same MUX
    assert "0-4" in slow  # Different MUX


# Schedule result serialization tests
def test_schedule_result_to_dict():
    """Test converting schedule result to dictionary."""
    result = CRScheduleResult(
        parallel_groups=[[("0", "1"), ("2", "3")]],
        metadata={"total_pairs": 2, "num_groups": 1},
        filtering_stats={"all_coupling_pairs": 5},
        cr_pairs_string=["0-1", "2-3"],
        qid_to_mux={"0": 0, "1": 0},
        mux_conflict_map={0: {1}},
    )

    result_dict = result.to_dict()

    assert "parallel_groups" in result_dict
    assert "metadata" in result_dict
    assert "filtering_stats" in result_dict
    assert result_dict["metadata"]["total_pairs"] == 2


def test_schedule_result_repr():
    """Test schedule result string representation."""
    result = CRScheduleResult(
        parallel_groups=[[("0", "1"), ("2", "3")]],
        metadata={"scheduled_pairs": 2, "num_groups": 1},
        filtering_stats={},
        cr_pairs_string=[],
        qid_to_mux={},
        mux_conflict_map={},
    )

    repr_str = repr(result)
    assert "pairs=2" in repr_str
    assert "groups=1" in repr_str


# Topology-based direction tests
def test_get_topology_direction_set_forward(scheduler):
    """Test topology direction set construction for forward direction."""
    # Create a mock topology with checkerboard_cr convention
    mock_topology = MagicMock()
    mock_topology.direction_convention = "checkerboard_cr"
    mock_topology.couplings = [[0, 1], [2, 3], [4, 5]]
    scheduler._topology = mock_topology

    result = scheduler._get_topology_direction_set(inverse=False)

    assert result == {"0-1", "2-3", "4-5"}


def test_get_topology_direction_set_inverse(scheduler):
    """Test topology direction set construction for inverse direction."""
    mock_topology = MagicMock()
    mock_topology.direction_convention = "checkerboard_cr"
    mock_topology.couplings = [[0, 1], [2, 3], [4, 5]]
    scheduler._topology = mock_topology

    result = scheduler._get_topology_direction_set(inverse=True)

    assert result == {"1-0", "3-2", "5-4"}


def test_get_topology_direction_set_no_convention(scheduler):
    """Test that non-checkerboard convention returns None."""
    mock_topology = MagicMock()
    mock_topology.direction_convention = "unspecified"
    mock_topology.couplings = [[0, 1], [2, 3]]
    scheduler._topology = mock_topology

    result = scheduler._get_topology_direction_set(inverse=False)

    assert result is None


def test_get_topology_direction_set_no_topology(scheduler):
    """Test that missing topology returns None (fallback)."""
    # Ensure _load_topology returns None (no topology_id on chip)
    scheduler._chip = MagicMock()
    scheduler._chip.topology_id = None

    result = scheduler._get_topology_direction_set(inverse=False)

    assert result is None


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_with_topology_direction(
    mock_load,
    mock_qubits,
    mock_couplings,
    scheduler,
    mock_chip,
    mock_qubit_models,
):
    """Test schedule generation using topology-based direction."""
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    # DB has both directions for each coupling
    mock_couplings.return_value = ["0-1", "1-0", "0-2", "2-0", "1-3", "3-1"]

    # Set up topology with checkerboard_cr convention
    mock_topology = MagicMock()
    mock_topology.direction_convention = "checkerboard_cr"
    mock_topology.couplings = [[0, 1], [0, 2], [1, 3]]
    scheduler._topology = mock_topology

    schedule = scheduler.generate(candidate_qubits=["0", "1", "2", "3"])

    assert schedule.metadata["direction_method"] == "topology"
    assert schedule.metadata["inverse"] is False

    # Only forward pairs should be selected
    all_pairs = [pair for group in schedule.parallel_groups for pair in group]
    assert ("0", "1") in all_pairs
    assert ("1", "0") not in all_pairs


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_with_topology_inverse(
    mock_load,
    mock_qubits,
    mock_couplings,
    scheduler,
    mock_chip,
    mock_qubit_models,
):
    """Test schedule generation with inverse=True using topology."""
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    # DB has both directions
    mock_couplings.return_value = ["0-1", "1-0", "0-2", "2-0", "1-3", "3-1"]

    # Topology: forward is [0,1], [0,2], [1,3]
    mock_topology = MagicMock()
    mock_topology.direction_convention = "checkerboard_cr"
    mock_topology.couplings = [[0, 1], [0, 2], [1, 3]]
    scheduler._topology = mock_topology

    schedule = scheduler.generate(candidate_qubits=["0", "1", "2", "3"], inverse=True)

    assert schedule.metadata["direction_method"] == "topology"
    assert schedule.metadata["inverse"] is True

    # Only inverse pairs should be selected
    all_pairs = [pair for group in schedule.parallel_groups for pair in group]
    assert ("1", "0") in all_pairs
    assert ("0", "1") not in all_pairs


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_fallback_without_topology(
    mock_load,
    mock_qubits,
    mock_couplings,
    scheduler,
    mock_chip,
    mock_qubit_models,
    mock_coupling_ids,
):
    """Test that generate falls back to measured when no topology is available."""
    mock_chip.topology_id = None
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    mock_couplings.return_value = mock_coupling_ids

    # No topology set
    scheduler._topology = None
    scheduler._chip = mock_chip

    schedule = scheduler.generate(candidate_qubits=["0", "1", "2", "3"])

    # Should fall back to measured since frequency data exists
    assert schedule.metadata["direction_method"] == "measured"
    assert schedule.metadata["inverse"] is False


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_measured_inverse(
    mock_load,
    mock_qubits,
    mock_couplings,
    scheduler,
    mock_chip,
    mock_qubit_models,
):
    """Test inverse with measured directionality (no topology)."""
    mock_chip.topology_id = None
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    # Frequencies: 0=5.0, 1=5.1, so 0-1 is forward (low→high), 1-0 is inverse (high→low)
    mock_couplings.return_value = ["0-1", "1-0"]

    scheduler._topology = None
    scheduler._chip = mock_chip

    schedule = scheduler.generate(candidate_qubits=["0", "1"], inverse=True)

    assert schedule.metadata["direction_method"] == "measured"
    assert schedule.metadata["inverse"] is True

    # Inverse: should select pair where freq[control] > freq[target]
    all_pairs = [pair for group in schedule.parallel_groups for pair in group]
    assert ("1", "0") in all_pairs
    assert ("0", "1") not in all_pairs
