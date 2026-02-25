"""Tests for 1-Qubit Scheduler.

These tests verify the OneQubitScheduler functionality including:
- Box type detection from module names
- MUX to box mapping
- Qubit grouping by box constraints
- Schedule generation with proper stage separation
"""

import pytest
import yaml
from qdash.workflow.engine.scheduler.one_qubit_scheduler import OneQubitScheduler
from qdash.workflow.engine.scheduler.one_qubit_types import (
    BOX_A,
    BOX_B,
    BOX_MIXED,
    OneQubitScheduleResult,
)


@pytest.fixture
def mock_wiring_config_64qv3():
    """Mock wiring configuration matching 64Qv3 structure."""
    return [
        # MUX 0: Uses B chassis (ctrl) and A chassis (read_out) → MIXED
        {
            "mux": 0,
            "ctrl": ["R21B-5", "R21B-0", "R21B-2", "R21B-6"],
            "read_out": "Q73A-1",
            "read_in": "Q73A-0",
            "pump": "Q73A-3",
        },
        # MUX 1: Uses A chassis only → Type A
        {
            "mux": 1,
            "ctrl": ["Q73A-2", "Q73A-4", "Q73A-9", "Q73A-11"],
            "read_out": "Q73A-8",
            "read_in": "Q73A-7",
            "pump": "Q73A-10",
        },
        # MUX 2: Uses A chassis only → Type A
        {
            "mux": 2,
            "ctrl": ["S159A-2", "S159A-4", "S159A-9", "S159A-11"],
            "read_out": "S159A-1",
            "read_in": "S159A-0",
            "pump": "S159A-3",
        },
        # MUX 3: Uses B chassis (ctrl) and A chassis (read_out) → MIXED
        {
            "mux": 3,
            "ctrl": ["U10B-5", "U10B-0", "U10B-2", "U10B-6"],
            "read_out": "S159A-8",
            "read_in": "S159A-7",
            "pump": "S159A-10",
        },
        # MUX 4: Uses B chassis (ctrl) and A chassis (read_out) → MIXED
        {
            "mux": 4,
            "ctrl": ["R21B-7", "R21B-11", "R21B-13", "R21B-8"],
            "read_out": "Q2A-8",
            "read_in": "Q2A-7",
            "pump": "Q2A-10",
        },
        # MUX 5: Uses A chassis only → Type A
        {
            "mux": 5,
            "ctrl": ["Q2A-2", "Q2A-4", "Q2A-9", "Q2A-11"],
            "read_out": "Q2A-1",
            "read_in": "Q2A-0",
            "pump": "Q2A-3",
        },
        # MUX 6: Uses A chassis only → Type A
        {
            "mux": 6,
            "ctrl": ["R20A-5", "R20A-6", "R20A-7", "R20A-8"],
            "read_out": "R20A-0",
            "read_in": "R20A-1",
            "pump": "R20A-2",
        },
        # MUX 7: Uses B chassis (ctrl) and A chassis (read_out) → MIXED
        {
            "mux": 7,
            "ctrl": ["U10B-7", "U10B-11", "U10B-13", "U10B-8"],
            "read_out": "R20A-13",
            "read_in": "R20A-12",
            "pump": "R20A-11",
        },
    ]


@pytest.fixture
def mock_wiring_config_simple():
    """Simple mock wiring configuration for basic testing."""
    return [
        # MUX 0: Type A only
        {
            "mux": 0,
            "ctrl": ["ModuleA-0", "ModuleA-1"],
            "read_out": "ReadA-0",
        },
        # MUX 1: Type B only
        {
            "mux": 1,
            "ctrl": ["ModuleB-0", "ModuleB-1"],
            "read_out": "ReadB-0",
        },
        # MUX 2: Mixed (A and B)
        {
            "mux": 2,
            "ctrl": ["ModuleA-2", "ModuleB-2"],
            "read_out": "ReadA-1",
        },
    ]


@pytest.fixture
def scheduler_64qv3(tmp_path, mock_wiring_config_64qv3):
    """Create OneQubitScheduler instance with 64Qv3-like configuration."""
    wiring_file = tmp_path / "wiring.yaml"
    wiring_file.write_text(yaml.dump({"64Qv3": mock_wiring_config_64qv3}))

    return OneQubitScheduler(chip_id="64Qv3", wiring_config_path=str(wiring_file))


@pytest.fixture
def scheduler_simple(tmp_path, mock_wiring_config_simple):
    """Create OneQubitScheduler instance with simple configuration."""
    wiring_file = tmp_path / "wiring.yaml"
    wiring_file.write_text(yaml.dump({"test_chip": mock_wiring_config_simple}))

    return OneQubitScheduler(chip_id="test_chip", wiring_config_path=str(wiring_file))


# ============================================================================
# Box Type Detection Tests
# ============================================================================


class TestBoxTypeExtraction:
    """Test box type extraction from module names."""

    def test_extract_box_a(self):
        """Test detection of Box A modules."""
        assert OneQubitScheduler._extract_box_type("Q73A-1") == BOX_A
        assert OneQubitScheduler._extract_box_type("R20A-5") == BOX_A
        assert OneQubitScheduler._extract_box_type("S159A-2") == BOX_A
        assert OneQubitScheduler._extract_box_type("ModuleA-0") == BOX_A

    def test_extract_box_b(self):
        """Test detection of Box B modules."""
        assert OneQubitScheduler._extract_box_type("R21B-5") == BOX_B
        assert OneQubitScheduler._extract_box_type("U10B-0") == BOX_B
        assert OneQubitScheduler._extract_box_type("U13B-7") == BOX_B
        assert OneQubitScheduler._extract_box_type("ModuleB-0") == BOX_B

    def test_extract_without_channel(self):
        """Test detection works without channel suffix."""
        assert OneQubitScheduler._extract_box_type("Q73A") == BOX_A
        assert OneQubitScheduler._extract_box_type("R21B") == BOX_B

    def test_extract_unrecognized(self):
        """Test handling of unrecognized module names."""
        assert OneQubitScheduler._extract_box_type("Unknown-1") is None
        assert OneQubitScheduler._extract_box_type("Module1-0") is None
        assert OneQubitScheduler._extract_box_type("") is None


# ============================================================================
# MUX Box Mapping Tests
# ============================================================================


class TestMuxBoxMapping:
    """Test MUX to box type mapping."""

    def test_build_mux_box_map_simple(self, scheduler_simple):
        """Test MUX box mapping with simple configuration."""
        wiring_config = scheduler_simple._load_wiring_config()
        mux_box_map = scheduler_simple._build_mux_box_map(wiring_config)

        # MUX 0: Box A only
        assert mux_box_map[0] == {BOX_A}

        # MUX 1: Box B only
        assert mux_box_map[1] == {BOX_B}

        # MUX 2: Mixed
        assert mux_box_map[2] == {BOX_A, BOX_B}

    def test_build_mux_box_map_64qv3(self, scheduler_64qv3):
        """Test MUX box mapping with 64Qv3 configuration."""
        wiring_config = scheduler_64qv3._load_wiring_config()
        mux_box_map = scheduler_64qv3._build_mux_box_map(wiring_config)

        # MUX 0: ctrl=R21B (B), read_out=Q73A (A) → Mixed
        assert BOX_A in mux_box_map[0]
        assert BOX_B in mux_box_map[0]

        # MUX 1: All A
        assert mux_box_map[1] == {BOX_A}

        # MUX 2: All A
        assert mux_box_map[2] == {BOX_A}

        # MUX 6: All A
        assert mux_box_map[6] == {BOX_A}


# ============================================================================
# Qubit to MUX Mapping Tests
# ============================================================================


class TestQubitToMuxMapping:
    """Test qubit ID to MUX ID mapping."""

    def test_qubit_to_mux_mapping(self, scheduler_simple):
        """Test qubit to MUX mapping (4 qubits per MUX)."""
        wiring_config = scheduler_simple._load_wiring_config()
        qid_to_mux = scheduler_simple._build_qubit_to_mux_map(wiring_config)

        # MUX 0: qubits 0, 1, 2, 3
        assert qid_to_mux["0"] == 0
        assert qid_to_mux["1"] == 0
        assert qid_to_mux["2"] == 0
        assert qid_to_mux["3"] == 0

        # MUX 1: qubits 4, 5, 6, 7
        assert qid_to_mux["4"] == 1
        assert qid_to_mux["5"] == 1
        assert qid_to_mux["6"] == 1
        assert qid_to_mux["7"] == 1

        # MUX 2: qubits 8, 9, 10, 11
        assert qid_to_mux["8"] == 2
        assert qid_to_mux["9"] == 2


# ============================================================================
# Schedule Generation Tests
# ============================================================================


class TestScheduleGeneration:
    """Test schedule generation with box constraints."""

    def test_generate_simple_schedule(self, scheduler_simple):
        """Test schedule generation with simple configuration."""
        # MUX 0 (qubits 0-3): Box A
        # MUX 1 (qubits 4-7): Box B
        # MUX 2 (qubits 8-11): Mixed

        schedule = scheduler_simple.generate(qids=["0", "4", "8"])

        assert isinstance(schedule, OneQubitScheduleResult)
        assert len(schedule.stages) == 3  # A, B, Mixed

        # Check metadata
        assert schedule.metadata["total_qubits"] == 3
        assert schedule.metadata["box_a_count"] == 1
        assert schedule.metadata["box_b_count"] == 1
        assert schedule.metadata["mixed_count"] == 1

    def test_generate_box_a_only(self, scheduler_simple):
        """Test schedule with only Box A qubits."""
        # Only qubits from MUX 0 (Box A)
        schedule = scheduler_simple.generate(qids=["0", "1", "2"])

        assert len(schedule.stages) == 1
        assert schedule.stages[0].box_type == BOX_A
        assert set(schedule.stages[0].qids) == {"0", "1", "2"}

    def test_generate_box_b_only(self, scheduler_simple):
        """Test schedule with only Box B qubits."""
        # Only qubits from MUX 1 (Box B)
        schedule = scheduler_simple.generate(qids=["4", "5", "6"])

        assert len(schedule.stages) == 1
        assert schedule.stages[0].box_type == BOX_B
        assert set(schedule.stages[0].qids) == {"4", "5", "6"}

    def test_generate_mixed_only(self, scheduler_simple):
        """Test schedule with only Mixed qubits."""
        # Only qubits from MUX 2 (Mixed)
        schedule = scheduler_simple.generate(qids=["8", "9", "10"])

        assert len(schedule.stages) == 1
        assert schedule.stages[0].box_type == BOX_MIXED
        assert set(schedule.stages[0].qids) == {"8", "9", "10"}

    def test_generate_preserves_order(self, scheduler_simple):
        """Test that qubit order is preserved within stages."""
        schedule = scheduler_simple.generate(qids=["2", "0", "1"])

        assert schedule.stages[0].qids == ["2", "0", "1"]

    def test_generate_64qv3_mixed_qubits(self, scheduler_64qv3):
        """Test schedule generation with 64Qv3 configuration."""
        # MUX 0 (qubits 0-3): Mixed
        # MUX 1 (qubits 4-7): Box A
        # MUX 6 (qubits 24-27): Box A

        schedule = scheduler_64qv3.generate(qids=["0", "4", "24"])

        assert schedule.metadata["box_a_count"] == 2  # qubits 4 and 24
        assert schedule.metadata["mixed_count"] == 1  # qubit 0

        # Box A stage should contain qubits 4 and 24
        box_a_stages = [s for s in schedule.stages if s.box_type == BOX_A]
        assert len(box_a_stages) == 1
        assert set(box_a_stages[0].qids) == {"4", "24"}

    def test_generate_empty_raises_error(self, scheduler_simple):
        """Test that empty qubit list raises ValueError."""
        with pytest.raises(ValueError, match="No qubits provided"):
            scheduler_simple.generate(qids=[])


# ============================================================================
# Serialization Tests
# ============================================================================


class TestSerialization:
    """Test serialization of schedule results."""

    def test_to_dict(self, scheduler_simple):
        """Test conversion to dictionary format."""
        schedule = scheduler_simple.generate(qids=["0", "4", "8"])

        result_dict = schedule.to_dict()

        assert "stages" in result_dict
        assert "metadata" in result_dict
        assert len(result_dict["stages"]) == 3

        for stage in result_dict["stages"]:
            assert "box_type" in stage
            assert "qids" in stage
            assert "mux_ids" in stage

    def test_repr(self, scheduler_simple):
        """Test string representation."""
        schedule = scheduler_simple.generate(qids=["0", "4", "8"])

        repr_str = repr(schedule)

        assert "OneQubitScheduleResult" in repr_str
        assert "qubits=3" in repr_str
        assert "stages=3" in repr_str


# ============================================================================
# MUX Info Tests
# ============================================================================


class TestMuxInfo:
    """Test MUX information retrieval."""

    def test_get_mux_info(self, scheduler_simple):
        """Test get_mux_info returns correct information."""
        mux_info = scheduler_simple.get_mux_info()

        assert 0 in mux_info
        assert 1 in mux_info
        assert 2 in mux_info

        # MUX 0: Box A
        assert mux_info[0]["box_label"] == "A"
        assert mux_info[0]["qids"] == ["0", "1", "2", "3"]

        # MUX 1: Box B
        assert mux_info[1]["box_label"] == "B"
        assert mux_info[1]["qids"] == ["4", "5", "6", "7"]

        # MUX 2: Mixed
        assert mux_info[2]["box_label"] == "A+B"
        assert mux_info[2]["qids"] == ["8", "9", "10", "11"]


# ============================================================================
# Generate from MUX Tests
# ============================================================================


class TestGenerateFromMux:
    """Test schedule generation from MUX IDs."""

    def test_generate_from_single_mux(self, scheduler_simple):
        """Test schedule generation from a single MUX ID."""
        schedule = scheduler_simple.generate_from_mux(mux_ids=[0])

        assert schedule.metadata["total_qubits"] == 4
        assert set(schedule.stages[0].qids) == {"0", "1", "2", "3"}

    def test_generate_from_multiple_mux(self, scheduler_simple):
        """Test schedule generation from multiple MUX IDs."""
        # MUX 0 (Box A) and MUX 1 (Box B)
        schedule = scheduler_simple.generate_from_mux(mux_ids=[0, 1])

        assert schedule.metadata["total_qubits"] == 8
        assert schedule.metadata["box_a_count"] == 4
        assert schedule.metadata["box_b_count"] == 4
        assert len(schedule.stages) == 2

    def test_generate_from_mux_preserves_order_within_stage(self, scheduler_simple):
        """Test that qubit order is preserved within each stage."""
        # MUX 0 (Box A) only - order should be preserved
        schedule = scheduler_simple.generate_from_mux(mux_ids=[0])

        assert schedule.stages[0].qids == ["0", "1", "2", "3"]

    def test_generate_from_mux_groups_by_box(self, scheduler_simple):
        """Test that qubits are grouped by box type across MUXes."""
        # MUX 1 (Box B) and MUX 0 (Box A) - should be in separate stages
        schedule = scheduler_simple.generate_from_mux(mux_ids=[1, 0])

        # Should have 2 stages (Box A and Box B)
        assert len(schedule.stages) == 2

        # Find Box A and Box B stages
        box_a_stage = next(s for s in schedule.stages if s.box_type == BOX_A)
        box_b_stage = next(s for s in schedule.stages if s.box_type == BOX_B)

        # MUX 0 qubits in Box A stage
        assert set(box_a_stage.qids) == {"0", "1", "2", "3"}
        # MUX 1 qubits in Box B stage
        assert set(box_b_stage.qids) == {"4", "5", "6", "7"}

    def test_generate_from_mux_empty_raises_error(self, scheduler_simple):
        """Test that empty MUX ID list raises ValueError."""
        with pytest.raises(ValueError, match="No MUX IDs provided"):
            scheduler_simple.generate_from_mux(mux_ids=[])

    def test_generate_from_mux_64qv3(self, scheduler_64qv3):
        """Test generate_from_mux with 64Qv3 configuration."""
        # MUX 1 (Box A) and MUX 0 (Mixed)
        schedule = scheduler_64qv3.generate_from_mux(mux_ids=[1, 0])

        assert schedule.metadata["total_qubits"] == 8
        assert schedule.metadata["box_a_count"] == 4  # MUX 1
        assert schedule.metadata["mixed_count"] == 4  # MUX 0

    def test_generate_from_mux_with_exclude_qids(self, scheduler_simple):
        """Test schedule generation with excluded qubit IDs."""
        # MUX 0 (Box A) has qubits 0,1,2,3 - exclude 1 and 3
        schedule = scheduler_simple.generate_from_mux(
            mux_ids=[0],
            exclude_qids=["1", "3"],
        )

        assert schedule.metadata["total_qubits"] == 2
        assert set(schedule.stages[0].qids) == {"0", "2"}

    def test_generate_from_mux_exclude_across_muxes(self, scheduler_simple):
        """Test excluding qubits across multiple MUXes."""
        # MUX 0 (Box A): 0,1,2,3
        # MUX 1 (Box B): 4,5,6,7
        schedule = scheduler_simple.generate_from_mux(
            mux_ids=[0, 1],
            exclude_qids=["2", "3", "5"],
        )

        assert schedule.metadata["total_qubits"] == 5
        # Box A: 0, 1 (2,3 excluded)
        # Box B: 4, 6, 7 (5 excluded)
        box_a_stage = next(s for s in schedule.stages if s.box_type == BOX_A)
        box_b_stage = next(s for s in schedule.stages if s.box_type == BOX_B)

        assert set(box_a_stage.qids) == {"0", "1"}
        assert set(box_b_stage.qids) == {"4", "6", "7"}

    def test_generate_from_mux_exclude_entire_mux(self, scheduler_simple):
        """Test excluding all qubits from one MUX."""
        # MUX 0 (Box A): 0,1,2,3 - all excluded
        # MUX 1 (Box B): 4,5,6,7 - none excluded
        schedule = scheduler_simple.generate_from_mux(
            mux_ids=[0, 1],
            exclude_qids=["0", "1", "2", "3"],
        )

        assert schedule.metadata["total_qubits"] == 4
        assert schedule.metadata["box_a_count"] == 0
        assert schedule.metadata["box_b_count"] == 4
        assert len(schedule.stages) == 1
        assert schedule.stages[0].box_type == BOX_B

    def test_generate_from_mux_exclude_all_raises_error(self, scheduler_simple):
        """Test that excluding all qubits raises ValueError."""
        with pytest.raises(ValueError, match="All qubits were excluded"):
            scheduler_simple.generate_from_mux(
                mux_ids=[0],
                exclude_qids=["0", "1", "2", "3"],
            )

    def test_generate_from_mux_exclude_non_matching(self, scheduler_simple):
        """Test that excluding non-matching qubits has no effect."""
        # MUX 0 has qubits 0,1,2,3 - exclude 100 (doesn't exist in MUX 0)
        schedule = scheduler_simple.generate_from_mux(
            mux_ids=[0],
            exclude_qids=["100", "200"],
        )

        assert schedule.metadata["total_qubits"] == 4
        assert set(schedule.stages[0].qids) == {"0", "1", "2", "3"}


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_wiring_config(self, tmp_path):
        """Test error when wiring config is missing."""
        scheduler = OneQubitScheduler(
            chip_id="nonexistent",
            wiring_config_path=str(tmp_path / "nonexistent.yaml"),
        )

        with pytest.raises(FileNotFoundError):
            scheduler.generate(qids=["0"])

    def test_qubit_not_in_mux_mapping(self, scheduler_simple):
        """Test handling of qubit IDs not in MUX mapping."""
        # Qubit 100 doesn't exist in our mock config (only MUX 0-2 = qubits 0-11)
        schedule = scheduler_simple.generate(qids=["0", "100"])

        # Qubit 100 should be treated as MIXED (conservative)
        assert schedule.metadata["mixed_count"] >= 1

    def test_single_qubit(self, scheduler_simple):
        """Test schedule generation with single qubit."""
        schedule = scheduler_simple.generate(qids=["0"])

        assert len(schedule.stages) == 1
        assert schedule.stages[0].qids == ["0"]
        assert schedule.metadata["total_qubits"] == 1


# ============================================================================
# Integration-like Tests
# ============================================================================


class TestIntegration:
    """Integration-like tests simulating real workflow usage."""

    def test_full_workflow_simulation(self, scheduler_64qv3):
        """Simulate a full calibration workflow with stage-based execution."""
        # Select qubits from different MUX types
        qids = ["0", "1", "4", "5", "8", "9", "24", "25"]

        schedule = scheduler_64qv3.generate(qids=qids)

        # Verify we can iterate through stages
        all_executed = []
        for stage in schedule.stages:
            # Within a stage, qubits execute sequentially
            for qid in stage.qids:
                all_executed.append(qid)

        # All qubits should be executed exactly once
        assert set(all_executed) == set(qids)
        assert len(all_executed) == len(qids)

    def test_stage_info_contains_mux_ids(self, scheduler_simple):
        """Test that stage info contains correct MUX IDs."""
        schedule = scheduler_simple.generate(qids=["0", "1", "4", "5"])

        for stage in schedule.stages:
            assert isinstance(stage.mux_ids, set)
            assert len(stage.mux_ids) > 0

            # All qubits in stage should belong to MUXes in mux_ids
            for qid in stage.qids:
                mux_id = schedule.qid_to_mux.get(qid)
                if mux_id is not None:
                    assert mux_id in stage.mux_ids

    def test_stage_info_contains_parallel_groups(self, scheduler_simple):
        """Test that stage info contains correct parallel groups (MUX-based)."""
        # Qubits from MUX 0 (0, 1) and MUX 1 (4, 5)
        schedule = scheduler_simple.generate(qids=["0", "1", "4", "5"])

        for stage in schedule.stages:
            assert isinstance(stage.parallel_groups, list)
            assert len(stage.parallel_groups) > 0

            # All qubits in stage should be in exactly one parallel group
            all_qids_in_groups = []
            for group in stage.parallel_groups:
                assert isinstance(group, list)
                all_qids_in_groups.extend(group)

            assert sorted(all_qids_in_groups) == sorted(stage.qids)

            # Each group should contain qubits from the same MUX
            for group in stage.parallel_groups:
                mux_ids = {schedule.qid_to_mux.get(qid) for qid in group}
                assert len(mux_ids) == 1  # All qubits in group from same MUX

    def test_parallel_groups_sorted_by_mux(self, scheduler_simple):
        """Test that parallel groups are sorted by MUX ID."""
        schedule = scheduler_simple.generate(qids=["4", "5", "0", "1"])  # MUX 1, MUX 0

        for stage in schedule.stages:
            if len(stage.parallel_groups) > 1:
                # Groups should be sorted by MUX ID
                mux_ids = []
                for group in stage.parallel_groups:
                    mux_id = schedule.qid_to_mux.get(group[0])
                    mux_ids.append(mux_id)
                assert mux_ids == sorted(mux_ids)

    def test_checkerboard_ordering_strategy(self, scheduler_simple):
        """Test scheduler with CheckerboardOrderingStrategy."""
        from qdash.workflow.engine.scheduler.one_qubit_plugins import (
            CheckerboardOrderingStrategy,
        )

        strategy = CheckerboardOrderingStrategy()
        schedule = scheduler_simple.generate(
            qids=["0", "1", "2", "3", "4", "5", "6", "7"],  # MUX 0 and 1
            ordering_strategy=strategy,
        )

        # Find stage with both MUXes
        for stage in schedule.stages:
            if len(stage.parallel_groups) >= 2:
                # MUX 0 (even): [0, 1, 2, 3]
                # MUX 1 (odd): [6, 7, 4, 5]
                mux0_group = None
                mux1_group = None
                for group in stage.parallel_groups:
                    if "0" in group:
                        mux0_group = group
                    if "4" in group or "6" in group:
                        mux1_group = group

                if mux0_group:
                    assert mux0_group == ["0", "1", "2", "3"]
                if mux1_group:
                    assert mux1_group == ["6", "7", "4", "5"]

    def test_generate_from_mux_with_ordering_strategy(self, scheduler_simple):
        """Test generate_from_mux with ordering strategy."""
        from qdash.workflow.engine.scheduler.one_qubit_plugins import (
            CheckerboardOrderingStrategy,
        )

        strategy = CheckerboardOrderingStrategy()
        schedule = scheduler_simple.generate_from_mux(
            mux_ids=[0, 1],
            ordering_strategy=strategy,
        )

        # Verify ordering is applied
        for stage in schedule.stages:
            for group in stage.parallel_groups:
                if "0" in group:
                    # MUX 0 (even): [0, 1, 2, 3]
                    assert group == ["0", "1", "2", "3"]
                elif "4" in group or "6" in group:
                    # MUX 1 (odd): [6, 7, 4, 5]
                    assert group == ["6", "7", "4", "5"]


class TestSynchronizedScheduling:
    """Tests for synchronized step-based scheduling."""

    def test_generate_synchronized_basic(self, scheduler_simple):
        """Test basic synchronized schedule generation."""
        schedule = scheduler_simple.generate_synchronized(
            qids=["0", "1", "2", "3", "4", "5", "6", "7"],
            use_checkerboard=True,
        )

        # Should have steps (number depends on box distribution)
        assert len(schedule.steps) > 0
        assert schedule.total_steps == len(schedule.steps)

        # Verify metadata
        assert schedule.metadata["total_qubits"] == 8
        assert schedule.metadata["use_checkerboard"] is True
        assert schedule.metadata["strategy"] == "checkerboard"

    def test_generate_synchronized_default_strategy(self, scheduler_simple):
        """Test synchronized schedule with default strategy."""
        schedule = scheduler_simple.generate_synchronized(
            qids=["0", "1", "2", "3", "4", "5", "6", "7"],
            use_checkerboard=False,
        )

        assert len(schedule.steps) > 0
        assert schedule.metadata["strategy"] == "default_synchronized"

    def test_synchronized_step_structure(self, scheduler_simple):
        """Test that synchronized steps have correct structure."""
        schedule = scheduler_simple.generate_synchronized(
            qids=["0", "1", "2", "3"],  # Only MUX 0
            use_checkerboard=True,
        )

        for step in schedule.steps:
            # Each step should have step_index, box_type, and parallel_qids
            assert hasattr(step, "step_index")
            assert hasattr(step, "box_type")
            assert hasattr(step, "parallel_qids")
            assert isinstance(step.parallel_qids, list)

    def test_synchronized_checkerboard_pattern(self, scheduler_simple):
        """Test that checkerboard pattern is applied correctly."""
        schedule = scheduler_simple.generate_synchronized(
            qids=["0", "1", "2", "3", "4", "5", "6", "7"],
            use_checkerboard=True,
        )

        # Collect all qids from steps
        all_qids = []
        for step in schedule.steps:
            all_qids.extend(step.parallel_qids)

        # All input qubits should be scheduled
        assert set(all_qids) == {"0", "1", "2", "3", "4", "5", "6", "7"}

    def test_synchronized_box_separation(self, scheduler_64qv3):
        """Test that synchronized schedule separates box types."""
        # Use scheduler with 64Qv3 config that has mixed boxes
        schedule = scheduler_64qv3.generate_synchronized(
            qids=["0", "1", "2", "3", "4", "5", "6", "7"],  # MUX 0 (MIXED) and MUX 1 (A)
            use_checkerboard=True,
        )

        # Should have different box types
        box_types = schedule.box_types
        assert len(box_types) > 0

    def test_generate_synchronized_from_mux(self, scheduler_simple):
        """Test synchronized schedule generation from MUX IDs."""
        schedule = scheduler_simple.generate_synchronized_from_mux(
            mux_ids=[0, 1],
            use_checkerboard=True,
        )

        # Should schedule 8 qubits (4 per MUX)
        total_qubits = sum(len(step.parallel_qids) for step in schedule.steps)
        assert total_qubits == 8

    def test_generate_synchronized_from_mux_with_exclude(self, scheduler_simple):
        """Test synchronized schedule with excluded qubits."""
        schedule = scheduler_simple.generate_synchronized_from_mux(
            mux_ids=[0, 1],
            exclude_qids=["0", "4"],
            use_checkerboard=True,
        )

        # Should schedule 6 qubits
        total_qubits = sum(len(step.parallel_qids) for step in schedule.steps)
        assert total_qubits == 6

        # Excluded qubits should not appear
        all_qids = []
        for step in schedule.steps:
            all_qids.extend(step.parallel_qids)
        assert "0" not in all_qids
        assert "4" not in all_qids

    def test_synchronized_result_to_dict(self, scheduler_simple):
        """Test serialization of synchronized result."""
        schedule = scheduler_simple.generate_synchronized(
            qids=["0", "1", "2", "3"],
            use_checkerboard=True,
        )

        result_dict = schedule.to_dict()

        assert "steps" in result_dict
        assert "metadata" in result_dict
        assert len(result_dict["steps"]) == len(schedule.steps)

        for step_dict in result_dict["steps"]:
            assert "step_index" in step_dict
            assert "box_type" in step_dict
            assert "parallel_qids" in step_dict

    def test_synchronized_get_steps_by_box(self, scheduler_64qv3):
        """Test filtering steps by box type."""
        schedule = scheduler_64qv3.generate_synchronized(
            qids=[str(i) for i in range(8)],
            use_checkerboard=True,
        )

        # Get steps by box type
        box_a_steps = schedule.get_steps_by_box(BOX_A)
        mixed_steps = schedule.get_steps_by_box(BOX_MIXED)

        # All returned steps should have the correct box type
        for step in box_a_steps:
            assert step.box_type == BOX_A
        for step in mixed_steps:
            assert step.box_type == BOX_MIXED

    def test_synchronized_empty_qids_raises(self, scheduler_simple):
        """Test that empty qids raises ValueError."""
        with pytest.raises(ValueError, match="No qubits provided"):
            scheduler_simple.generate_synchronized(qids=[], use_checkerboard=True)

    def test_synchronized_from_mux_empty_raises(self, scheduler_simple):
        """Test that empty mux_ids raises ValueError."""
        with pytest.raises(ValueError, match="No MUX IDs provided"):
            scheduler_simple.generate_synchronized_from_mux(
                mux_ids=[],
                use_checkerboard=True,
            )

    def test_synchronized_repr(self, scheduler_simple):
        """Test string representation of synchronized result."""
        schedule = scheduler_simple.generate_synchronized(
            qids=["0", "1", "2", "3"],
            use_checkerboard=True,
        )

        repr_str = repr(schedule)
        assert "SynchronizedOneQubitScheduleResult" in repr_str
        assert "qubits=" in repr_str
        assert "steps=" in repr_str

    def test_synchronized_step_repr(self, scheduler_simple):
        """Test string representation of synchronized step."""
        schedule = scheduler_simple.generate_synchronized(
            qids=["0", "1", "2", "3"],
            use_checkerboard=True,
        )

        if schedule.steps:
            step = schedule.steps[0]
            repr_str = repr(step)
            assert "Step(" in repr_str


class TestBoxBModuleSharing:
    """Tests for Box B module sharing in synchronized scheduling."""

    def test_box_b_module_map_construction(self, scheduler_64qv3):
        """Test Box B module map is built correctly."""
        wiring_config = scheduler_64qv3._load_wiring_config()
        box_b_map = scheduler_64qv3._build_box_b_module_map(wiring_config)

        # Mock 64Qv3 config has 2 Box B modules: R21B, U10B (8 MUXes only)
        assert "R21B" in box_b_map
        assert "U10B" in box_b_map

        # Each Box B module controls 2 MUXes
        assert len(box_b_map["R21B"]) == 2
        assert len(box_b_map["U10B"]) == 2

        # Verify specific MUX assignments
        assert box_b_map["R21B"] == [0, 4]
        assert box_b_map["U10B"] == [3, 7]

    def test_mixed_mux_grouping(self, scheduler_64qv3):
        """Test MIXED MUXes are grouped correctly by Box B sharing."""
        wiring_config = scheduler_64qv3._load_wiring_config()
        box_b_map = scheduler_64qv3._build_box_b_module_map(wiring_config)

        # MIXED MUXes in mock config: 0, 3, 4, 7
        mixed_mux_ids = [0, 3, 4, 7]

        groups = scheduler_64qv3._group_mixed_muxes_by_box_b(mixed_mux_ids, box_b_map)

        # Should have 2 groups (since each Box B module has 2 MUXes)
        assert len(groups) == 2

        # Group 0: first MUX from each Box B module (0, 3)
        # Group 1: second MUX from each Box B module (4, 7)
        assert 0 in groups[0]
        assert 3 in groups[0]

        assert 4 in groups[1]
        assert 7 in groups[1]

    def test_synchronized_mixed_8_steps(self, scheduler_64qv3):
        """Test that MIXED scheduling generates 8 steps (4 steps × 2 groups)."""
        # Use all MIXED MUXes from mock config (0, 3, 4, 7)
        mixed_qids = []
        for mux_id in [0, 3, 4, 7]:
            for offset in range(4):
                mixed_qids.append(str(mux_id * 4 + offset))

        schedule = scheduler_64qv3.generate_synchronized(
            qids=mixed_qids,
            use_checkerboard=True,
        )

        # All qubits are MIXED, so should have 8 steps
        mixed_steps = schedule.get_steps_by_box(BOX_MIXED)
        assert len(mixed_steps) == 8

    def test_mock_config_12_steps(self, scheduler_64qv3):
        """Test mock config calibration generates 12 steps (4 A + 8 MIXED)."""
        # Mock config has 8 MUXes: 0-7
        # MUXes 1, 2, 5, 6 are Box A only
        # MUXes 0, 3, 4, 7 are MIXED
        schedule = scheduler_64qv3.generate_synchronized(
            qids=[str(i) for i in range(32)],  # 8 MUXes × 4 qubits
            use_checkerboard=True,
        )

        # Should have 12 steps total (4 A + 8 MIXED)
        assert schedule.total_steps == 12

        # Box A: 4 steps (4 MUXes)
        box_a_steps = schedule.get_steps_by_box(BOX_A)
        assert len(box_a_steps) == 4

        # MIXED: 8 steps (4 MUXes in 2 groups × 4 steps)
        mixed_steps = schedule.get_steps_by_box(BOX_MIXED)
        assert len(mixed_steps) == 8

    def test_mixed_steps_no_box_b_sharing_conflict(self, scheduler_64qv3):
        """Test that MUXes sharing Box B module are in different step groups."""
        schedule = scheduler_64qv3.generate_synchronized(
            qids=[str(i) for i in range(32)],  # 8 MUXes
            use_checkerboard=True,
        )

        wiring_config = scheduler_64qv3._load_wiring_config()
        box_b_map = scheduler_64qv3._build_box_b_module_map(wiring_config)
        qid_to_mux = scheduler_64qv3._build_qubit_to_mux_map(wiring_config)

        # Check that within each step, no two qubits share a Box B module
        mixed_steps = schedule.get_steps_by_box(BOX_MIXED)

        for step in mixed_steps:
            # Get MUX IDs in this step
            mux_ids_in_step = {qid_to_mux[qid] for qid in step.parallel_qids}

            # Check no Box B module conflict
            for module_id, mux_list in box_b_map.items():
                # Count how many MUXes from this Box B module are in the step
                count = sum(1 for m in mux_list if m in mux_ids_in_step)
                assert count <= 1, (
                    f"Step {step.step_index} has {count} MUXes sharing {module_id}: "
                    f"{[m for m in mux_list if m in mux_ids_in_step]}"
                )
