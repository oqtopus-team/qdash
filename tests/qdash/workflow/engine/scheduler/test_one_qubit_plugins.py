"""Tests for 1-Qubit Scheduler Ordering Plugins."""

import pytest

from qdash.workflow.engine.scheduler.one_qubit_plugins import (
    CheckerboardOrderingStrategy,
    DefaultOrderingStrategy,
    DefaultSynchronizedStrategy,
    OrderingContext,
)


@pytest.fixture
def context_64q():
    """Create context for 64-qubit chip."""
    qid_to_mux = {str(i): i // 4 for i in range(64)}
    return OrderingContext(
        chip_id="64Qv3",
        grid_size=8,
        mux_grid_size=4,
        qid_to_mux=qid_to_mux,
    )


class TestDefaultOrderingStrategy:
    """Tests for DefaultOrderingStrategy."""

    def test_natural_order(self, context_64q):
        """Test that qubits are returned in natural order."""
        strategy = DefaultOrderingStrategy()

        # MUX 0
        result = strategy.order_qids_in_mux(0, ["0", "1", "2", "3"], context_64q)
        assert result == ["0", "1", "2", "3"]

        # MUX 1
        result = strategy.order_qids_in_mux(1, ["4", "5", "6", "7"], context_64q)
        assert result == ["4", "5", "6", "7"]

    def test_partial_mux(self, context_64q):
        """Test ordering with partial qubit set."""
        strategy = DefaultOrderingStrategy()

        result = strategy.order_qids_in_mux(0, ["2", "0"], context_64q)
        assert result == ["0", "2"]

    def test_metadata(self):
        """Test metadata returns expected fields."""
        strategy = DefaultOrderingStrategy()
        metadata = strategy.get_metadata()

        assert metadata["strategy_name"] == "default"
        assert "description" in metadata

    def test_repr(self):
        """Test string representation."""
        strategy = DefaultOrderingStrategy()
        assert "DefaultOrderingStrategy" in repr(strategy)


class TestCheckerboardOrderingStrategy:
    """Tests for CheckerboardOrderingStrategy."""

    def test_even_mux_order(self, context_64q):
        """Test that even MUXes use [0, 1, 2, 3] offset order."""
        strategy = CheckerboardOrderingStrategy()

        # MUX 0 (even): offsets [0, 1, 2, 3] -> qids [0, 1, 2, 3]
        result = strategy.order_qids_in_mux(0, ["0", "1", "2", "3"], context_64q)
        assert result == ["0", "1", "2", "3"]

        # MUX 2 (even): offsets [0, 1, 2, 3] -> qids [8, 9, 10, 11]
        result = strategy.order_qids_in_mux(2, ["8", "9", "10", "11"], context_64q)
        assert result == ["8", "9", "10", "11"]

    def test_odd_mux_order(self, context_64q):
        """Test that odd MUXes use [2, 3, 0, 1] offset order."""
        strategy = CheckerboardOrderingStrategy()

        # MUX 1 (odd): offsets [2, 3, 0, 1] -> qids [6, 7, 4, 5]
        result = strategy.order_qids_in_mux(1, ["4", "5", "6", "7"], context_64q)
        assert result == ["6", "7", "4", "5"]

        # MUX 3 (odd): offsets [2, 3, 0, 1] -> qids [14, 15, 12, 13]
        result = strategy.order_qids_in_mux(3, ["12", "13", "14", "15"], context_64q)
        assert result == ["14", "15", "12", "13"]

    def test_partial_mux_even(self, context_64q):
        """Test ordering with partial qubit set for even MUX."""
        strategy = CheckerboardOrderingStrategy()

        # MUX 0 with only qubits 0 and 2
        result = strategy.order_qids_in_mux(0, ["0", "2"], context_64q)
        assert result == ["0", "2"]

        # MUX 0 with only qubits 1 and 3
        result = strategy.order_qids_in_mux(0, ["3", "1"], context_64q)
        assert result == ["1", "3"]

    def test_partial_mux_odd(self, context_64q):
        """Test ordering with partial qubit set for odd MUX."""
        strategy = CheckerboardOrderingStrategy()

        # MUX 1 with only qubits 4 and 6
        # Offset order [2, 3, 0, 1] -> qid order [6, 7, 4, 5]
        result = strategy.order_qids_in_mux(1, ["4", "6"], context_64q)
        assert result == ["6", "4"]

    def test_checkerboard_pattern_step1(self, context_64q):
        """Test that step 1 creates correct checkerboard pattern."""
        strategy = CheckerboardOrderingStrategy()

        # Collect first qubit from each MUX
        step1_qids = []
        for mux_id in range(16):
            base = mux_id * 4
            qids = [str(base + i) for i in range(4)]
            ordered = strategy.order_qids_in_mux(mux_id, qids, context_64q)
            step1_qids.append(ordered[0])

        # Expected: [0, 6, 8, 14, 16, 22, 24, 30, 32, 38, 40, 46, 48, 54, 56, 62]
        expected = [
            "0",
            "6",
            "8",
            "14",
            "16",
            "22",
            "24",
            "30",
            "32",
            "38",
            "40",
            "46",
            "48",
            "54",
            "56",
            "62",
        ]
        assert step1_qids == expected

    def test_checkerboard_pattern_all_steps(self, context_64q):
        """Test that all 4 steps create correct patterns."""
        strategy = CheckerboardOrderingStrategy()

        # Expected patterns from PDF
        expected_steps = [
            [
                "0",
                "6",
                "8",
                "14",
                "16",
                "22",
                "24",
                "30",
                "32",
                "38",
                "40",
                "46",
                "48",
                "54",
                "56",
                "62",
            ],
            [
                "1",
                "7",
                "9",
                "15",
                "17",
                "23",
                "25",
                "31",
                "33",
                "39",
                "41",
                "47",
                "49",
                "55",
                "57",
                "63",
            ],
            [
                "2",
                "4",
                "10",
                "12",
                "18",
                "20",
                "26",
                "28",
                "34",
                "36",
                "42",
                "44",
                "50",
                "52",
                "58",
                "60",
            ],
            [
                "3",
                "5",
                "11",
                "13",
                "19",
                "21",
                "27",
                "29",
                "35",
                "37",
                "43",
                "45",
                "51",
                "53",
                "59",
                "61",
            ],
        ]

        for step in range(4):
            step_qids = []
            for mux_id in range(16):
                base = mux_id * 4
                qids = [str(base + i) for i in range(4)]
                ordered = strategy.order_qids_in_mux(mux_id, qids, context_64q)
                step_qids.append(ordered[step])

            assert step_qids == expected_steps[step], f"Step {step + 1} mismatch"

    def test_metadata(self):
        """Test metadata returns expected fields."""
        strategy = CheckerboardOrderingStrategy()
        metadata = strategy.get_metadata()

        assert metadata["strategy_name"] == "checkerboard"
        assert metadata["even_mux_order"] == [0, 1, 2, 3]
        assert metadata["odd_mux_order"] == [2, 3, 0, 1]

    def test_repr(self):
        """Test string representation."""
        strategy = CheckerboardOrderingStrategy()
        assert "CheckerboardOrderingStrategy" in repr(strategy)


class TestOrderingContext:
    """Tests for OrderingContext."""

    def test_default_values(self):
        """Test context with default values."""
        context = OrderingContext(
            chip_id="64Qv3",
            grid_size=8,
            mux_grid_size=4,
        )

        assert context.chip_id == "64Qv3"
        assert context.grid_size == 8
        assert context.mux_grid_size == 4
        assert context.qid_to_mux == {}

    def test_with_qid_mapping(self):
        """Test context with qubit to MUX mapping."""
        qid_to_mux = {"0": 0, "1": 0, "4": 1, "5": 1}
        context = OrderingContext(
            chip_id="64Qv3",
            grid_size=8,
            mux_grid_size=4,
            qid_to_mux=qid_to_mux,
        )

        assert context.qid_to_mux["0"] == 0
        assert context.qid_to_mux["4"] == 1


class TestCheckerboardSynchronizedSteps:
    """Tests for CheckerboardOrderingStrategy.generate_synchronized_steps."""

    def test_synchronized_steps_full_chip(self, context_64q):
        """Test synchronized steps for full 64-qubit chip."""
        strategy = CheckerboardOrderingStrategy()

        mux_ids = list(range(16))
        qids = [str(i) for i in range(64)]

        steps = strategy.generate_synchronized_steps(mux_ids, qids, context_64q)

        assert len(steps) == 4

        # Expected patterns
        expected_steps = [
            [
                "0",
                "6",
                "8",
                "14",
                "16",
                "22",
                "24",
                "30",
                "32",
                "38",
                "40",
                "46",
                "48",
                "54",
                "56",
                "62",
            ],
            [
                "1",
                "7",
                "9",
                "15",
                "17",
                "23",
                "25",
                "31",
                "33",
                "39",
                "41",
                "47",
                "49",
                "55",
                "57",
                "63",
            ],
            [
                "2",
                "4",
                "10",
                "12",
                "18",
                "20",
                "26",
                "28",
                "34",
                "36",
                "42",
                "44",
                "50",
                "52",
                "58",
                "60",
            ],
            [
                "3",
                "5",
                "11",
                "13",
                "19",
                "21",
                "27",
                "29",
                "35",
                "37",
                "43",
                "45",
                "51",
                "53",
                "59",
                "61",
            ],
        ]

        for i, step in enumerate(steps):
            assert step == expected_steps[i], f"Step {i} mismatch"

    def test_synchronized_steps_subset_muxes(self, context_64q):
        """Test synchronized steps for subset of MUXes."""
        strategy = CheckerboardOrderingStrategy()

        # Only MUXes 0 and 1
        mux_ids = [0, 1]
        qids = [str(i) for i in range(8)]

        steps = strategy.generate_synchronized_steps(mux_ids, qids, context_64q)

        assert len(steps) == 4

        # MUX 0 (even): [0, 1, 2, 3]
        # MUX 1 (odd):  [6, 7, 4, 5]
        expected_steps = [
            ["0", "6"],  # Step 0
            ["1", "7"],  # Step 1
            ["2", "4"],  # Step 2
            ["3", "5"],  # Step 3
        ]

        for i, step in enumerate(steps):
            assert step == expected_steps[i], f"Step {i} mismatch"

    def test_synchronized_steps_partial_qids(self, context_64q):
        """Test synchronized steps with partial qubit set."""
        strategy = CheckerboardOrderingStrategy()

        mux_ids = [0, 1]
        # Only include some qubits
        qids = ["0", "1", "4", "5"]

        steps = strategy.generate_synchronized_steps(mux_ids, qids, context_64q)

        # Should filter out empty steps
        assert len(steps) <= 4

        # Verify included qubits
        all_qids = []
        for step in steps:
            all_qids.extend(step)
        assert set(all_qids) == {"0", "1", "4", "5"}

    def test_synchronized_steps_each_step_has_16_qubits(self, context_64q):
        """Test that each step has 16 qubits (one per MUX) for full chip."""
        strategy = CheckerboardOrderingStrategy()

        mux_ids = list(range(16))
        qids = [str(i) for i in range(64)]

        steps = strategy.generate_synchronized_steps(mux_ids, qids, context_64q)

        for i, step in enumerate(steps):
            assert len(step) == 16, f"Step {i} should have 16 qubits"


class TestDefaultSynchronizedStrategy:
    """Tests for DefaultSynchronizedStrategy."""

    def test_natural_order(self, context_64q):
        """Test natural order for individual MUX."""
        strategy = DefaultSynchronizedStrategy()

        result = strategy.order_qids_in_mux(0, ["0", "1", "2", "3"], context_64q)
        assert result == ["0", "1", "2", "3"]

    def test_synchronized_steps_natural_order(self, context_64q):
        """Test synchronized steps use natural ordering."""
        strategy = DefaultSynchronizedStrategy()

        mux_ids = [0, 1]
        qids = [str(i) for i in range(8)]

        steps = strategy.generate_synchronized_steps(mux_ids, qids, context_64q)

        assert len(steps) == 4

        # Natural order: MUX 0 -> [0,1,2,3], MUX 1 -> [4,5,6,7]
        expected_steps = [
            ["0", "4"],  # offset 0 from each MUX
            ["1", "5"],  # offset 1
            ["2", "6"],  # offset 2
            ["3", "7"],  # offset 3
        ]

        for i, step in enumerate(steps):
            assert step == expected_steps[i], f"Step {i} mismatch"

    def test_metadata(self):
        """Test metadata returns expected fields."""
        strategy = DefaultSynchronizedStrategy()
        metadata = strategy.get_metadata()

        assert metadata["strategy_name"] == "default_synchronized"
        assert "description" in metadata

    def test_repr(self):
        """Test string representation."""
        strategy = DefaultSynchronizedStrategy()
        assert "DefaultSynchronizedStrategy" in repr(strategy)
