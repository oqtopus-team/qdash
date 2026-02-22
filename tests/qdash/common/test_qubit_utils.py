"""Tests for qdash.common.qubit_utils module."""

from unittest.mock import MagicMock, patch

import pytest
from qdash.common.qubit_utils import (
    DEFAULT_NUM_QUBITS,
    _get_chip_size,
    qid_to_label,
    qid_to_label_from_chip,
)


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


class TestQidToLabelFromChip:
    """Tests for qid_to_label_from_chip function."""

    def setup_method(self) -> None:
        """Clear lru_cache before each test."""
        _get_chip_size.cache_clear()

    @patch("qdash.repository.MongoChipRepository")
    def test_64q_chip(self, mock_repo_cls: MagicMock) -> None:
        chip = MagicMock(size=64)
        mock_repo_cls.return_value.find_by_id.return_value = chip
        assert qid_to_label_from_chip("16", project_id="p1", chip_id="64Q") == "Q16"

    @patch("qdash.repository.MongoChipRepository")
    def test_144q_chip(self, mock_repo_cls: MagicMock) -> None:
        chip = MagicMock(size=144)
        mock_repo_cls.return_value.find_by_id.return_value = chip
        assert qid_to_label_from_chip("16", project_id="p1", chip_id="144Q") == "Q016"

    @patch("qdash.repository.MongoChipRepository")
    def test_coupling_qid(self, mock_repo_cls: MagicMock) -> None:
        chip = MagicMock(size=64)
        mock_repo_cls.return_value.find_by_id.return_value = chip
        assert qid_to_label_from_chip("16-22", project_id="p1", chip_id="64Q") == "Q16-Q22"

    @patch("qdash.repository.MongoChipRepository")
    def test_coupling_qid_144q(self, mock_repo_cls: MagicMock) -> None:
        chip = MagicMock(size=144)
        mock_repo_cls.return_value.find_by_id.return_value = chip
        assert qid_to_label_from_chip("5-16", project_id="p1", chip_id="144Q") == "Q005-Q016"

    @patch("qdash.repository.MongoChipRepository")
    def test_chip_not_found_defaults(self, mock_repo_cls: MagicMock) -> None:
        mock_repo_cls.return_value.find_by_id.return_value = None
        result = qid_to_label_from_chip("5", project_id="p1", chip_id="unknown")
        assert result == "Q05"  # defaults to 64 qubits -> 2-digit padding

    @patch("qdash.repository.MongoChipRepository")
    def test_cache_avoids_repeated_db_calls(self, mock_repo_cls: MagicMock) -> None:
        chip = MagicMock(size=64)
        mock_repo_cls.return_value.find_by_id.return_value = chip

        qid_to_label_from_chip("0", project_id="p1", chip_id="64Q")
        qid_to_label_from_chip("1", project_id="p1", chip_id="64Q")
        qid_to_label_from_chip("2", project_id="p1", chip_id="64Q")

        # DB should be called only once due to caching
        assert mock_repo_cls.return_value.find_by_id.call_count == 1


class TestGetChipSize:
    """Tests for _get_chip_size function."""

    def setup_method(self) -> None:
        _get_chip_size.cache_clear()

    @patch("qdash.repository.MongoChipRepository")
    def test_returns_chip_size(self, mock_repo_cls: MagicMock) -> None:
        chip = MagicMock(size=144)
        mock_repo_cls.return_value.find_by_id.return_value = chip
        assert _get_chip_size("p1", "144Q") == 144

    @patch("qdash.repository.MongoChipRepository")
    def test_returns_default_when_not_found(self, mock_repo_cls: MagicMock) -> None:
        mock_repo_cls.return_value.find_by_id.return_value = None
        assert _get_chip_size("p1", "missing") == DEFAULT_NUM_QUBITS
