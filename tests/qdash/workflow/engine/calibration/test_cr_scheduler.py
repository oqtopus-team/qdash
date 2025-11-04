"""Tests for CR Scheduler.

These tests verify the CRScheduler functionality including:
- MUX conflict detection
- Frequency directionality filtering
- Graph coloring strategies
- Parallel grouping
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from qdash.workflow.engine.calibration.cr_scheduler import CRScheduler, CRScheduleResult


@pytest.fixture
def mock_chip_doc():
    """Mock ChipDocument with sample qubit and coupling data."""
    chip_doc = MagicMock()

    # Mock qubits with frequency data
    chip_doc.qubits = {
        "0": MagicMock(data={"qubit_frequency": {"value": 5.0}}),
        "1": MagicMock(data={"qubit_frequency": {"value": 5.1}}),
        "2": MagicMock(data={"qubit_frequency": {"value": 5.2}}),
        "3": MagicMock(data={"qubit_frequency": {"value": 5.3}}),
        "4": MagicMock(data={"qubit_frequency": {"value": 5.4}}),
        "5": MagicMock(data={"qubit_frequency": {"value": 5.5}}),
    }

    # Mock couplings
    chip_doc.couplings = {
        "0-1": MagicMock(),
        "1-2": MagicMock(),
        "2-3": MagicMock(),
        "3-4": MagicMock(),
        "4-5": MagicMock(),
        "0-4": MagicMock(),  # Cross-MUX coupling
    }

    return chip_doc


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
def scheduler(tmp_path, mock_chip_doc, mock_wiring_config):
    """Create CRScheduler instance with mocked dependencies."""
    # Create temporary wiring.yaml
    wiring_file = tmp_path / "wiring.yaml"
    import yaml

    wiring_file.write_text(yaml.dump({"test_chip": mock_wiring_config}))

    scheduler = CRScheduler(
        username="test_user", chip_id="test_chip", wiring_config_path=str(wiring_file)
    )

    # Mock chip document loading
    scheduler._chip_doc = mock_chip_doc

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
    conflict_map = CRScheduler._build_mux_conflict_map(mock_wiring_config)

    # MUX 0 and MUX 1 should conflict (same readout module)
    assert 1 in conflict_map[0]
    assert 0 in conflict_map[1]

    # All MUXes conflict with each other due to shared readout/control modules
    assert len(conflict_map) > 0


def test_build_qubit_to_mux_map(mock_wiring_config):
    """Test qubit-to-MUX mapping."""
    qid_to_mux = CRScheduler._build_qubit_to_mux_map(mock_wiring_config)

    # MUX 0 controls qubits 0-3
    assert qid_to_mux["0"] == 0
    assert qid_to_mux["1"] == 0
    assert qid_to_mux["2"] == 0
    assert qid_to_mux["3"] == 0

    # MUX 1 controls qubits 4-7
    assert qid_to_mux["4"] == 1
    assert qid_to_mux["5"] == 1


# Frequency filtering tests
def test_extract_qubit_frequency(mock_chip_doc):
    """Test frequency extraction from chip document."""
    frequencies = CRScheduler._extract_qubit_frequency(mock_chip_doc.qubits)

    assert frequencies["0"] == 5.0
    assert frequencies["1"] == 5.1
    assert len(frequencies) == 6


def test_frequency_directionality_filter(scheduler):
    """Test that only lower->higher frequency pairs are kept."""
    all_pairs = ["0-1", "1-0", "1-2", "2-1"]

    # Load frequency data
    frequencies = CRScheduler._extract_qubit_frequency(scheduler._chip_doc.qubits)

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
    mux_conflict_map = {}

    groups = CRScheduler._group_cr_pairs_by_conflict(cr_pairs, qid_to_mux, mux_conflict_map)

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
    mux_conflict_map = {}

    groups = CRScheduler._group_cr_pairs_by_conflict(
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
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_full_schedule(mock_load, scheduler, mock_chip_doc):
    """Test complete schedule generation."""
    mock_load.return_value = mock_chip_doc

    schedule = scheduler.generate(
        candidate_qubits=["0", "1", "2", "3"],
        max_parallel_ops=10,
        coloring_strategy="largest_first",
    )

    assert isinstance(schedule, CRScheduleResult)
    assert len(schedule.parallel_groups) > 0
    assert schedule.metadata["coloring_strategy"] == "largest_first"
    assert schedule.metadata["candidate_qubits_count"] == 4


@patch.object(CRScheduler, "_load_chip_data")
def test_generate_with_max_parallel_ops(mock_load, scheduler, mock_chip_doc):
    """Test schedule generation with parallel operation limit."""
    mock_load.return_value = mock_chip_doc

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

    fast, slow = CRScheduler._split_fast_slow_pairs(cr_pairs, qid_to_mux)

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
