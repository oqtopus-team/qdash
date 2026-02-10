"""Tests for CR Scheduler Plugin Architecture.

These tests verify the pluggable filter and scheduler architecture including:
- Filter pipeline execution
- Custom filter implementations
- Custom scheduler implementations
- Integration with CRScheduler
"""

from unittest.mock import MagicMock, patch

import pytest
from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler
from qdash.workflow.engine.scheduler.plugins import (
    CandidateQubitFilter,
    FidelityFilter,
    FilterContext,
    FrequencyDirectionalityFilter,
    IntraThenInterMuxScheduler,
    MuxConflictScheduler,
    ScheduleContext,
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
        "0": MagicMock(data={"qubit_frequency": {"value": 5.0}, "x90_fidelity": {"value": 0.98}}),
        "1": MagicMock(data={"qubit_frequency": {"value": 5.1}, "x90_fidelity": {"value": 0.97}}),
        "2": MagicMock(data={"qubit_frequency": {"value": 5.2}, "x90_fidelity": {"value": 0.96}}),
        "3": MagicMock(data={"qubit_frequency": {"value": 5.3}, "x90_fidelity": {"value": 0.92}}),
        "4": MagicMock(data={"qubit_frequency": {"value": 5.4}, "x90_fidelity": {"value": 0.91}}),
        "5": MagicMock(data={"qubit_frequency": {"value": 5.5}, "x90_fidelity": {"value": 0.90}}),
    }


@pytest.fixture
def mock_coupling_ids():
    """Mock coupling IDs from individual CouplingDocument collection."""
    return ["0-1", "1-2", "2-3", "3-4", "4-5", "0-4"]


@pytest.fixture
def filter_context(mock_chip, mock_qubit_models):
    """Create FilterContext for testing."""
    return FilterContext(
        chip=mock_chip,
        grid_size=8,
        qubit_frequency={"0": 5.0, "1": 5.1, "2": 5.2, "3": 5.3, "4": 5.4, "5": 5.5},
        qid_to_mux={"0": 0, "1": 0, "2": 0, "3": 0, "4": 1, "5": 1},
        qubit_models=mock_qubit_models,
    )


@pytest.fixture
def schedule_context():
    """Create ScheduleContext for testing."""
    return ScheduleContext(
        qid_to_mux={"0": 0, "1": 0, "2": 0, "3": 0, "4": 1, "5": 1},
        mux_conflict_map={0: {1}, 1: {0}},  # MUX 0 and 1 conflict
    )


# ============================================================================
# Filter Tests
# ============================================================================


def test_candidate_qubit_filter_with_candidates(filter_context):
    """Test CandidateQubitFilter with specific candidates."""
    filter_obj = CandidateQubitFilter(["0", "1", "2"])
    pairs = ["0-1", "1-2", "2-3", "3-4"]

    filtered = filter_obj.filter(pairs, filter_context)

    assert "0-1" in filtered
    assert "1-2" in filtered
    assert "2-3" not in filtered  # 3 not in candidates
    assert "3-4" not in filtered

    stats = filter_obj.get_stats()
    assert stats["input_pairs"] == 4
    assert stats["output_pairs"] == 2
    assert stats["candidate_qubits_count"] == 3


def test_candidate_qubit_filter_none_candidates(filter_context):
    """Test CandidateQubitFilter with None (no filtering)."""
    filter_obj = CandidateQubitFilter(None)
    pairs = ["0-1", "1-2", "2-3"]

    filtered = filter_obj.filter(pairs, filter_context)

    assert filtered == pairs

    stats = filter_obj.get_stats()
    assert stats["input_pairs"] == 3
    assert stats["output_pairs"] == 3
    assert stats["candidate_qubits_count"] is None


def test_frequency_directionality_filter_measured(filter_context):
    """Test FrequencyDirectionalityFilter with measured frequencies."""
    filter_obj = FrequencyDirectionalityFilter(use_design_based=False)
    pairs = ["0-1", "1-0", "1-2", "2-1"]

    filtered = filter_obj.filter(pairs, filter_context)

    # Only pairs with increasing frequency should pass
    assert "0-1" in filtered  # 5.0 < 5.1
    assert "1-2" in filtered  # 5.1 < 5.2
    assert "1-0" not in filtered  # 5.1 > 5.0
    assert "2-1" not in filtered  # 5.2 > 5.1

    stats = filter_obj.get_stats()
    assert stats["method"] == "measured"


def test_frequency_directionality_filter_design_based(filter_context):
    """Test FrequencyDirectionalityFilter with design-based inference."""
    filter_obj = FrequencyDirectionalityFilter(use_design_based=True)
    pairs = ["0-1", "1-0", "0-2", "2-0"]

    filtered = filter_obj.filter(pairs, filter_context)

    # Check based on checkerboard pattern
    # 0: (0,0) → sum=0 (even) → low freq
    # 1: (0,1) → sum=1 (odd) → high freq
    # 2: (1,0) → sum=1 (odd) → high freq
    assert "0-1" in filtered  # low → high ✓
    assert "0-2" in filtered  # low → high ✓
    assert "1-0" not in filtered  # high → low ✗
    assert "2-0" not in filtered  # high → low ✗

    stats = filter_obj.get_stats()
    assert stats["method"] == "design_based"


def test_fidelity_filter(filter_context):
    """Test FidelityFilter with threshold."""
    filter_obj = FidelityFilter(min_fidelity=0.95)
    pairs = ["0-1", "1-2", "2-3", "3-4"]

    filtered = filter_obj.filter(pairs, filter_context)

    # 0: 0.98 ✓, 1: 0.97 ✓, 2: 0.96 ✓, 3: 0.92 ✗, 4: 0.91 ✗
    assert "0-1" in filtered  # Both ≥ 0.95
    assert "1-2" in filtered  # Both ≥ 0.95
    assert "2-3" not in filtered  # 3 < 0.95
    assert "3-4" not in filtered  # Both < 0.95

    stats = filter_obj.get_stats()
    assert stats["min_fidelity"] == 0.95
    assert stats["output_pairs"] == 2


# ============================================================================
# Scheduler Tests
# ============================================================================


def test_mux_conflict_scheduler(schedule_context):
    """Test MuxConflictScheduler."""
    scheduler = MuxConflictScheduler(max_parallel_ops=10, coloring_strategy="largest_first")
    pairs = ["0-1", "2-3", "4-5"]  # 0-1, 2-3 same MUX, 4-5 different MUX

    groups = scheduler.schedule(pairs, schedule_context)

    # All three pairs should be schedulable (no direct conflicts in this simple case)
    assert len(groups) > 0
    total_pairs = sum(len(g) for g in groups)
    assert total_pairs == 3

    metadata = scheduler.get_metadata()
    assert metadata["scheduler_name"] == "mux_conflict"
    assert metadata["coloring_strategy"] == "largest_first"


def test_intra_then_inter_mux_scheduler(schedule_context):
    """Test IntraThenInterMuxScheduler."""
    inner_scheduler = MuxConflictScheduler(max_parallel_ops=10)
    scheduler = IntraThenInterMuxScheduler(inner_scheduler=inner_scheduler)

    # 0-1 and 2-3 are intra-MUX, 0-4 is inter-MUX
    pairs = ["0-1", "2-3", "0-4"]

    groups = scheduler.schedule(pairs, schedule_context)

    # Should have both intra-MUX and inter-MUX groups
    assert len(groups) > 0

    metadata = scheduler.get_metadata()
    assert metadata["scheduler_name"] == "intra_then_inter_mux"
    assert metadata["intra_mux_pairs"] == 2
    assert metadata["inter_mux_pairs"] == 1


# ============================================================================
# Integration Tests
# ============================================================================


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
@patch.object(CRScheduler, "_load_wiring_config")
def test_generate_with_plugins_default(
    mock_wiring,
    mock_load,
    mock_qubits,
    mock_couplings,
    mock_chip,
    mock_qubit_models,
    mock_coupling_ids,
    tmp_path,
):
    """Test generate_with_plugins with default filters and scheduler."""
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    mock_couplings.return_value = mock_coupling_ids

    # Mock wiring config
    wiring_config = [
        {"mux": 0, "read_out": "R0", "ctrl": ["C0", "C1"]},
        {"mux": 1, "read_out": "R1", "ctrl": ["C2", "C3"]},
    ]
    mock_wiring.return_value = wiring_config

    scheduler = CRScheduler(
        username="test", chip_id="64Qv3", wiring_config_path=str(tmp_path / "wiring.yaml")
    )

    # Use default plugins
    schedule = scheduler.generate_with_plugins()

    assert len(schedule.parallel_groups) > 0
    assert "scheduler" in schedule.metadata
    assert "filters" in schedule.metadata
    assert "filter_pipeline" in schedule.filtering_stats


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
@patch.object(CRScheduler, "_load_wiring_config")
def test_generate_with_plugins_custom_filters(
    mock_wiring,
    mock_load,
    mock_qubits,
    mock_couplings,
    mock_chip,
    mock_qubit_models,
    mock_coupling_ids,
    tmp_path,
):
    """Test generate_with_plugins with custom filter pipeline."""
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    mock_couplings.return_value = mock_coupling_ids

    wiring_config = [
        {"mux": 0, "read_out": "R0", "ctrl": ["C0", "C1"]},
        {"mux": 1, "read_out": "R1", "ctrl": ["C2", "C3"]},
    ]
    mock_wiring.return_value = wiring_config

    scheduler = CRScheduler(
        username="test", chip_id="64Qv3", wiring_config_path=str(tmp_path / "wiring.yaml")
    )

    # Custom filter pipeline
    filters = [
        CandidateQubitFilter(["0", "1", "2", "3"]),
        FrequencyDirectionalityFilter(use_design_based=False),
        FidelityFilter(min_fidelity=0.95),
    ]

    schedule = scheduler.generate_with_plugins(filters=filters)

    assert len(schedule.parallel_groups) >= 0  # May be 0 if filters are too strict
    assert len(schedule.filtering_stats["filter_pipeline"]) == 3

    # Check that all filters were applied
    filter_names = [stat["filter_name"] for stat in schedule.filtering_stats["filter_pipeline"]]
    assert "candidate_qubit" in filter_names
    assert "frequency_directionality" in filter_names
    assert "fidelity" in filter_names


@patch.object(CRScheduler, "_load_coupling_ids")
@patch.object(CRScheduler, "_load_qubit_models")
@patch.object(CRScheduler, "_load_chip_data")
@patch.object(CRScheduler, "_load_wiring_config")
def test_generate_with_plugins_custom_scheduler(
    mock_wiring,
    mock_load,
    mock_qubits,
    mock_couplings,
    mock_chip,
    mock_qubit_models,
    mock_coupling_ids,
    tmp_path,
):
    """Test generate_with_plugins with custom scheduler."""
    mock_load.return_value = mock_chip
    mock_qubits.return_value = mock_qubit_models
    mock_couplings.return_value = mock_coupling_ids

    wiring_config = [
        {"mux": 0, "read_out": "R0", "ctrl": ["C0", "C1"]},
        {"mux": 1, "read_out": "R1", "ctrl": ["C2", "C3"]},
    ]
    mock_wiring.return_value = wiring_config

    scheduler_obj = CRScheduler(
        username="test", chip_id="64Qv3", wiring_config_path=str(tmp_path / "wiring.yaml")
    )

    # Custom scheduler
    custom_scheduler = IntraThenInterMuxScheduler(
        inner_scheduler=MuxConflictScheduler(max_parallel_ops=5, coloring_strategy="smallest_last")
    )

    schedule = scheduler_obj.generate_with_plugins(scheduler=custom_scheduler)

    assert len(schedule.parallel_groups) > 0
    assert schedule.metadata["scheduler"]["scheduler_name"] == "intra_then_inter_mux"
    assert "intra_mux_pairs" in schedule.metadata["scheduler"]
    assert "inter_mux_pairs" in schedule.metadata["scheduler"]


# ============================================================================
# Filter Repr Tests
# ============================================================================


def test_filter_repr():
    """Test filter string representations."""
    assert "CandidateQubitFilter(qubits=3)" in repr(CandidateQubitFilter(["0", "1", "2"]))
    assert "FrequencyDirectionalityFilter(method=design, inverse=False)" in repr(
        FrequencyDirectionalityFilter(use_design_based=True)
    )
    assert "FidelityFilter(min=0.95)" in repr(FidelityFilter(min_fidelity=0.95))


def test_scheduler_repr():
    """Test scheduler string representations."""
    mux_scheduler = MuxConflictScheduler(max_parallel_ops=10, coloring_strategy="largest_first")
    assert "MuxConflictScheduler" in repr(mux_scheduler)

    intra_inter_scheduler = IntraThenInterMuxScheduler(inner_scheduler=mux_scheduler)
    assert "IntraThenInterMuxScheduler" in repr(intra_inter_scheduler)
