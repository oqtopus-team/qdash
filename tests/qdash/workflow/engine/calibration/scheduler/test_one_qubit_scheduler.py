"""Tests for 1-Qubit Scheduler.

These tests verify the OneQubitScheduler functionality including:
- Box type detection from module names
- MUX to box mapping
- Qubit grouping by box constraints
- Schedule generation with proper stage separation
"""

import pytest
import yaml

from qdash.workflow.engine.calibration.scheduler.one_qubit_scheduler import (
    BOX_A,
    BOX_B,
    BOX_MIXED,
    OneQubitScheduler,
    OneQubitScheduleResult,
    OneQubitStageInfo,
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
