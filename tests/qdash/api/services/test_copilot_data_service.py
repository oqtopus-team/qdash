"""Tests for copilot_data_service heatmap and available parameters methods."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

from qdash.common.copilot.runtime import FALLBACK_QUERY_LIMIT, CopilotRuntime
from qdash.common.copilot.settings import AnalysisConfig, CopilotConfig, ModelConfig


class TestLoadChipHeatmapValidation:
    """Tests for load_chip_heatmap input validation and error handling."""

    def setup_method(self):
        self.service = CopilotRuntime()

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
        self.service = CopilotRuntime()

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
        self.service = CopilotRuntime()

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


class TestLoadChipParameterTimeseries:
    """Tests for per-chip parameter timeseries aggregation."""

    def _doc(self, qid: str, value: float, start_at: str, unit: str = "us") -> MagicMock:
        doc = MagicMock()
        doc.qid = qid
        doc.start_at.isoformat.return_value = start_at
        doc.output_parameters = {"t1": {"value": value, "unit": unit}}
        return doc

    def test_returns_error_when_no_data_found(self):
        data_access = MagicMock()
        data_access.load_chip_parameter_timeseries_docs.return_value = []
        service = CopilotRuntime(data_access=data_access)

        result = service.load_chip_parameter_timeseries("t1", "chip-1")

        assert result == {"error": "No data for 't1' on chip 'chip-1'"}

    def test_builds_qubit_and_chip_statistics(self):
        data_access = MagicMock()
        data_access.load_chip_parameter_timeseries_docs.return_value = [
            self._doc("1", 12.0, "2025-01-01T12:00:00"),
            self._doc("0", 10.0, "2025-01-01T10:00:00"),
            self._doc("0", 8.0, "2025-01-01T09:00:00"),
            self._doc("1", 12.1, "2025-01-01T11:00:00"),
        ]
        service = CopilotRuntime(data_access=data_access)

        result = service.load_chip_parameter_timeseries("t1", "chip-1", last_n=2)

        assert result["chip_id"] == "chip-1"
        assert result["parameter_name"] == "t1"
        assert result["unit"] == "us"
        assert result["num_qubits"] == 2
        assert result["statistics"]["count"] == 2
        assert result["statistics"]["mean"] == 11
        assert result["statistics"]["median"] == 11
        assert result["statistics"]["min"] == 10
        assert result["statistics"]["max"] == 12
        assert "stdev" in result["statistics"]
        assert [qubit["qid"] for qubit in result["qubits"]] == ["0", "1"]
        assert result["qubits"][0]["latest"] == 10
        assert result["qubits"][0]["trend"] == "up"
        assert result["qubits"][1]["latest"] == 12
        assert result["qubits"][1]["trend"] == "stable"
        assert result["timeseries"] == [
            {"qid": "0", "t": "2025-01-01T09:00:00", "v": 8.0},
            {"qid": "0", "t": "2025-01-01T10:00:00", "v": 10.0},
            {"qid": "1", "t": "2025-01-01T11:00:00", "v": 12.1},
            {"qid": "1", "t": "2025-01-01T12:00:00", "v": 12.0},
        ]

    def test_non_numeric_latest_is_excluded_from_chip_statistics(self):
        data_access = MagicMock()
        doc = MagicMock()
        doc.qid = "0"
        doc.start_at.isoformat.return_value = "2025-01-01T10:00:00"
        doc.output_parameters = {"t1": {"value": "bad", "unit": "us"}}
        data_access.load_chip_parameter_timeseries_docs.return_value = [doc]
        service = CopilotRuntime(data_access=data_access)

        result = service.load_chip_parameter_timeseries("t1", "chip-1")

        assert result["statistics"] == {
            "count": 0,
            "mean": 0,
            "median": 0,
            "min": 0,
            "max": 0,
        }
        assert result["qubits"][0]["latest"] == "bad"


class TestLoadChipSummary:
    """Tests for chip-level qubit summary aggregation."""

    def _doc(self, qid: str, data: dict[str, object]) -> MagicMock:
        doc = MagicMock()
        doc.qid = qid
        doc.data = data
        return doc

    def test_returns_error_when_chip_has_no_qubits(self):
        data_access = MagicMock()
        data_access.load_qubits_for_chip.return_value = []
        service = CopilotRuntime(data_access=data_access)

        result = service.load_chip_summary("chip-1")

        assert result == {"error": "No qubits found for chip_id=chip-1"}

    def test_builds_statistics_and_uniform_qubit_rows(self):
        data_access = MagicMock()
        data_access.load_qubits_for_chip.return_value = [
            self._doc("1", {"t1": {"value": 12.0}, "label": "good"}),
            self._doc("0", {"t1": {"value": 10.0}, "label": "best", "t2": {"value": 7.0}}),
        ]
        service = CopilotRuntime(data_access=data_access)

        result = service.load_chip_summary("chip-1")

        assert result["chip_id"] == "chip-1"
        assert result["num_qubits"] == 2
        assert result["statistics"]["t1"] == {
            "mean": 11,
            "median": 11,
            "stdev": 1.414,
            "min": 10,
            "max": 12,
            "count": 2,
        }
        assert result["statistics"]["t2"] == {
            "mean": 7,
            "median": 7,
            "stdev": 0.0,
            "min": 7,
            "max": 7,
            "count": 1,
        }
        assert result["qubits"] == [
            {"qid": "0", "label": "best", "t1": 10.0, "t2": 7.0},
            {"qid": "1", "label": "good", "t1": 12.0, "t2": None},
        ]

    def test_parameter_filter_applies_before_statistics(self):
        data_access = MagicMock()
        data_access.load_qubits_for_chip.return_value = [
            self._doc("0", {"t1": {"value": 10.0}, "t2": {"value": 7.0}}),
        ]
        service = CopilotRuntime(data_access=data_access)

        result = service.load_chip_summary("chip-1", param_names=["t2"])

        assert result["statistics"] == {
            "t2": {
                "mean": 7,
                "median": 7,
                "stdev": 0.0,
                "min": 7,
                "max": 7,
                "count": 1,
            }
        }
        assert result["qubits"] == [{"qid": "0", "t2": 7.0}]


class TestBuildAnalysisContext:
    """Tests for analysis context assembly."""

    def _config(self, *, multimodal: bool) -> CopilotConfig:
        return CopilotConfig(
            enabled=True,
            model=ModelConfig(provider="openai", name="gpt-4.1"),
            analysis=AnalysisConfig(enabled=True, multimodal=multimodal, max_expected_images=2),
        )

    def test_builds_context_with_related_knowledge(self):
        service = CopilotRuntime(data_access=MagicMock())
        knowledge = MagicMock()
        knowledge.to_prompt.return_value = "Prompt body"
        history_context = MagicMock(type="history", last_n=3)
        neighbor_context = MagicMock(type="neighbor_qubits", params=["t1"])
        coupling_context = MagicMock(type="coupling", params=["g"])
        knowledge.related_context = [history_context, neighbor_context, coupling_context]

        with (
            patch.object(service, "load_qubit_params", return_value={"f01": 5.0}),
            patch.object(
                service,
                "load_task_result",
                return_value={
                    "input_parameters": {"drive_amp": 0.1},
                    "output_parameters": {"t1": {"value": 12.0}},
                    "run_parameters": {"shots": 1024},
                    "figure_path": ["/tmp/figure.png"],
                },
            ),
            patch.object(service, "load_task_history", return_value=[{"task_id": "older"}]),
            patch.object(service, "load_neighbor_qubit_params", return_value={"1": {"t1": 9.0}}),
            patch.object(service, "load_coupling_params", return_value={"0-1": {"g": 0.02}}),
            patch("qdash.datamodel.task_knowledge.get_task_knowledge", return_value=knowledge),
        ):
            result = service.build_analysis_context(
                task_name="CheckT1",
                chip_id="chip-1",
                qid="0",
                task_id="task-1",
                image_base64=None,
                config=self._config(multimodal=False),
            )

        assert result.context.task_knowledge_prompt == "Prompt body"
        assert result.context.qubit_params == {"f01": 5.0}
        assert result.context.input_parameters == {"drive_amp": 0.1}
        assert result.context.output_parameters == {"t1": {"value": 12.0}}
        assert result.context.run_parameters == {"shots": 1024}
        assert result.context.history_results == [{"task_id": "older"}]
        assert result.context.neighbor_qubit_params == {"1": {"t1": 9.0}}
        assert result.context.coupling_params == {"0-1": {"g": 0.02}}
        assert result.figure_paths == ["/tmp/figure.png"]
        assert result.image_base64 is None
        assert result.expected_images == []

    def test_multimodal_context_loads_missing_figure_and_expected_images(self):
        service = CopilotRuntime(data_access=MagicMock())
        knowledge = MagicMock()
        knowledge.to_prompt.return_value = "Prompt body"
        knowledge.related_context = []

        with (
            patch.object(service, "load_qubit_params", return_value={}),
            patch.object(
                service,
                "load_task_result",
                return_value={
                    "input_parameters": {},
                    "output_parameters": {},
                    "run_parameters": {},
                    "figure_path": ["/tmp/figure.png"],
                },
            ),
            patch.object(
                service, "load_figure_as_base64", return_value="encoded-image"
            ) as load_fig,
            patch.object(
                service,
                "collect_expected_images",
                return_value=[("img-1", "expected alt")],
            ) as collect_expected,
            patch("qdash.datamodel.task_knowledge.get_task_knowledge", return_value=knowledge),
        ):
            result = service.build_analysis_context(
                task_name="CheckT1",
                chip_id="chip-1",
                qid="0",
                task_id="task-1",
                image_base64=None,
                config=self._config(multimodal=True),
            )

        load_fig.assert_called_once_with(["/tmp/figure.png"])
        collect_expected.assert_called_once_with(knowledge, max_images=2)
        assert result.image_base64 == "encoded-image"
        assert result.expected_images == [("img-1", "expected alt")]
