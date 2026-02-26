"""Tests for copilot_data_service heatmap and available parameters methods."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

from qdash.api.services.copilot_data_service import FALLBACK_QUERY_LIMIT, CopilotDataService


class TestLoadChipHeatmapValidation:
    """Tests for load_chip_heatmap input validation and error handling."""

    def setup_method(self):
        self.service = CopilotDataService()

    @patch("qdash.api.lib.metrics_config.load_metrics_config")
    @patch("qdash.api.lib.metrics_config.get_qubit_metric_metadata", return_value=None)
    def test_unknown_metric_returns_error(self, _mock_meta, mock_config):
        mock_config.return_value = MagicMock(qubit_metrics={"t1": None, "t2_echo": None})
        result = self.service.load_chip_heatmap("chip-1", "nonexistent_metric")
        assert "error" in result
        assert "Unknown qubit metric" in result["error"]
        assert "nonexistent_metric" in result["error"]

    @patch("qdash.dbmodel.chip.ChipDocument")
    @patch("qdash.api.lib.metrics_config.get_qubit_metric_metadata")
    def test_chip_not_found_returns_error(self, mock_meta, mock_chip_doc):
        mock_meta.return_value = MagicMock()
        mock_chip_doc.find_one.return_value.run.return_value = None
        result = self.service.load_chip_heatmap("nonexistent", "t1")
        assert "error" in result
        assert "not found" in result["error"]

    @patch("qdash.repository.task_result_history.MongoTaskResultHistoryRepository")
    @patch("qdash.common.topology_config.load_topology")
    @patch("qdash.dbmodel.chip.ChipDocument")
    @patch("qdash.api.lib.metrics_config.get_qubit_metric_metadata")
    def test_no_data_returns_error(self, mock_meta, mock_chip_doc, _mock_topo, mock_repo):
        meta = MagicMock()
        meta.evaluation.mode = "maximize"
        meta.scale = 1.0
        meta.title = "T1"
        meta.unit = "µs"
        mock_meta.return_value = meta

        chip = MagicMock()
        chip.project_id = "proj-1"
        chip.topology_id = None
        chip.size = 4
        mock_chip_doc.find_one.return_value.run.return_value = chip

        mock_repo.return_value.aggregate_latest_metrics.return_value = {"t1": {}}

        result = self.service.load_chip_heatmap("chip-1", "t1")
        assert "error" in result
        assert "No data found" in result["error"]

    @patch("qdash.repository.task_result_history.MongoTaskResultHistoryRepository")
    @patch("qdash.common.topology_config.load_topology")
    @patch("qdash.dbmodel.chip.ChipDocument")
    @patch("qdash.api.lib.metrics_config.get_qubit_metric_metadata")
    def test_topology_load_failure_falls_back_to_grid(
        self, mock_meta, mock_chip_doc, mock_topo, mock_repo
    ):
        """When topology loading fails, should fall back to sqrt-based grid."""
        meta = MagicMock()
        meta.evaluation.mode = "maximize"
        meta.scale = 1.0
        meta.title = "T1"
        meta.unit = "µs"
        mock_meta.return_value = meta

        chip = MagicMock()
        chip.project_id = "proj-1"
        chip.topology_id = "bad-topology"
        chip.size = 4
        mock_chip_doc.find_one.return_value.run.return_value = chip

        mock_topo.side_effect = FileNotFoundError("not found")

        mock_repo.return_value.aggregate_latest_metrics.return_value = {
            "t1": {
                "0": {"value": 45.0, "execution_id": "e1"},
            }
        }

        result = self.service.load_chip_heatmap("chip-1", "t1")
        assert "error" not in result
        assert "chart" in result

    @patch("qdash.repository.task_result_history.MongoTaskResultHistoryRepository")
    @patch("qdash.dbmodel.chip.ChipDocument")
    @patch("qdash.api.lib.metrics_config.get_qubit_metric_metadata")
    def test_aggregation_error_returns_error(self, mock_meta, mock_chip_doc, mock_repo):
        meta = MagicMock()
        meta.evaluation.mode = "maximize"
        mock_meta.return_value = meta

        chip = MagicMock()
        chip.project_id = "proj-1"
        chip.topology_id = None
        chip.size = 4
        mock_chip_doc.find_one.return_value.run.return_value = chip

        mock_repo.return_value.aggregate_latest_metrics.side_effect = ValueError("DB error")

        result = self.service.load_chip_heatmap("chip-1", "t1")
        assert "error" in result
        assert "Failed to aggregate" in result["error"]


class TestLoadChipHeatmapSuccess:
    """Tests for load_chip_heatmap successful execution paths."""

    def setup_method(self):
        self.service = CopilotDataService()

    @patch("qdash.repository.task_result_history.MongoTaskResultHistoryRepository")
    @patch("qdash.dbmodel.chip.ChipDocument")
    @patch("qdash.api.lib.metrics_config.get_qubit_metric_metadata")
    def test_successful_heatmap_has_chart_and_statistics(self, mock_meta, mock_chip_doc, mock_repo):
        meta = MagicMock()
        meta.evaluation.mode = "maximize"
        meta.scale = 1e-6
        meta.title = "T1"
        meta.unit = "µs"
        mock_meta.return_value = meta

        chip = MagicMock()
        chip.project_id = "proj-1"
        chip.topology_id = None
        chip.size = 4
        mock_chip_doc.find_one.return_value.run.return_value = chip

        mock_repo.return_value.aggregate_latest_metrics.return_value = {
            "t1": {
                "0": {"value": 45e6, "execution_id": "e1"},
                "1": {"value": 50e6, "execution_id": "e1"},
            }
        }

        result = self.service.load_chip_heatmap("chip-1", "t1")
        assert "error" not in result
        assert "chart" in result
        assert "data" in result["chart"]
        assert "layout" in result["chart"]
        assert "statistics" in result
        stats = result["statistics"]
        assert stats["count"] == 2
        assert "mean" in stats
        assert "median" in stats
        assert not math.isnan(stats["mean"])


class TestLoadAvailableParameters:
    """Tests for load_available_parameters method."""

    def setup_method(self):
        self.service = CopilotDataService()

    @patch("qdash.dbmodel.task_result_history.TaskResultHistoryDocument")
    def test_empty_results_returns_error(self, mock_doc):
        mock_doc.get_motor_collection.return_value.distinct.return_value = []
        result = self.service.load_available_parameters("chip-1")
        assert "error" in result
        assert "No output parameters" in result["error"]

    @patch("qdash.dbmodel.task_result_history.TaskResultHistoryDocument")
    def test_successful_listing(self, mock_doc):
        mock_doc.get_motor_collection.return_value.distinct.return_value = [
            "t1",
            "qubit_frequency",
            "t2_echo",
        ]
        result = self.service.load_available_parameters("chip-1")
        assert "error" not in result
        assert result["parameter_names"] == ["qubit_frequency", "t1", "t2_echo"]
        assert result["count"] == 3

    @patch("qdash.dbmodel.task_result_history.TaskResultHistoryDocument")
    def test_with_qid_filter(self, mock_doc):
        mock_doc.get_motor_collection.return_value.distinct.return_value = ["t1"]
        result = self.service.load_available_parameters("chip-1", qid="0")
        assert result["qid"] == "0"

    @patch("qdash.dbmodel.task_result_history.TaskResultHistoryDocument")
    def test_fallback_on_distinct_failure(self, mock_doc):
        """When distinct() fails, should fall back to manual scan."""
        mock_doc.get_motor_collection.return_value.distinct.side_effect = AttributeError(
            "no distinct"
        )

        doc1 = MagicMock()
        doc1.output_parameter_names = ["t1", "qubit_frequency"]
        doc2 = MagicMock()
        doc2.output_parameter_names = ["t2_echo", "t1"]
        mock_doc.find.return_value.limit.return_value.run.return_value = [doc1, doc2]

        result = self.service.load_available_parameters("chip-1")
        assert "error" not in result
        assert "t1" in result["parameter_names"]
        assert "qubit_frequency" in result["parameter_names"]
        assert "t2_echo" in result["parameter_names"]
        mock_doc.find.return_value.limit.assert_called_with(FALLBACK_QUERY_LIMIT)

    @patch("qdash.dbmodel.task_result_history.TaskResultHistoryDocument")
    def test_empty_results_with_qid_mentions_qid(self, mock_doc):
        mock_doc.get_motor_collection.return_value.distinct.return_value = []
        result = self.service.load_available_parameters("chip-1", qid="5")
        assert "error" in result
        assert "qid=5" in result["error"]
