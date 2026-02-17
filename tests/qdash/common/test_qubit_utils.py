"""Tests for qdash.common.qubit_utils module."""

import pytest
from qdash.common.qubit_utils import qid_to_label


class TestQidToLabel:
    """Tests for qid_to_label function."""

    def test_64q_system_single_digit(self) -> None:
        assert qid_to_label("5", 64) == "Q05"

    def test_64q_system_double_digit(self) -> None:
        assert qid_to_label("63", 64) == "Q63"

    def test_64q_system_zero(self) -> None:
        assert qid_to_label("0", 64) == "Q00"

    def test_144q_system_single_digit(self) -> None:
        assert qid_to_label("5", 144) == "Q005"

    def test_144q_system_double_digit(self) -> None:
        assert qid_to_label("63", 144) == "Q063"

    def test_144q_system_triple_digit(self) -> None:
        assert qid_to_label("143", 144) == "Q143"

    def test_144q_system_zero(self) -> None:
        assert qid_to_label("0", 144) == "Q000"

    def test_1000q_system(self) -> None:
        assert qid_to_label("5", 1000) == "Q0005"

    def test_small_system_minimum_two_digits(self) -> None:
        assert qid_to_label("3", 5) == "Q03"

    def test_10q_system(self) -> None:
        assert qid_to_label("9", 10) == "Q09"

    def test_100q_system(self) -> None:
        assert qid_to_label("5", 100) == "Q005"

    def test_invalid_qid_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid qid format"):
            qid_to_label("Q00", 64)

    def test_non_numeric_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid qid format"):
            qid_to_label("abc", 64)

    def test_empty_string_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid qid format"):
            qid_to_label("", 64)
