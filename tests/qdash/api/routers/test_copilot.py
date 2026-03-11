"""Tests for copilot provenance lineage graph tool and data store."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from qdash.api.lib.ai_labels import TOOL_LABELS
from qdash.api.lib.copilot_agent import AGENT_TOOLS, _build_llm_summary, _wrap_tool_executors
from qdash.api.services.copilot_data_service import CopilotDataService

if TYPE_CHECKING:
    from qdash.api.schemas.provenance import LineageResponse


class TestProvenanceLineageGraphValidation:
    """Tests for entity_id format validation and max_depth bounds."""

    def setup_method(self):
        self.service = CopilotDataService()

    def test_empty_entity_id_returns_error(self):
        result = self.service.load_provenance_lineage_graph("", "chip-1")
        assert "error" in result
        assert "Invalid entity_id format" in result["error"]

    def test_entity_id_too_few_colons_returns_error(self):
        result = self.service.load_provenance_lineage_graph("param:qid", "chip-1")
        assert "error" in result
        assert "Invalid entity_id format" in result["error"]

    def test_entity_id_too_many_colons_returns_error(self):
        result = self.service.load_provenance_lineage_graph("a:b:c:d:e", "chip-1")
        assert "error" in result
        assert "Invalid entity_id format" in result["error"]

    @patch.object(CopilotDataService, "_resolve_project_id", return_value=None)
    def test_missing_chip_returns_descriptive_error(self, _mock_resolve):
        result = self.service.load_provenance_lineage_graph(
            "param:0:exec-1:task-1", "nonexistent-chip"
        )
        assert "error" in result
        assert "nonexistent-chip" in result["error"]
        assert "may not exist" in result["error"]

    @patch.object(CopilotDataService, "_resolve_project_id", return_value="proj-1")
    @patch.object(CopilotDataService, "_get_provenance_service")
    def test_max_depth_clamped_to_upper_bound(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        """max_depth > 20 should be clamped to 20."""
        mock_service = MagicMock()
        mock_lineage = _make_empty_lineage("param:0:exec-1:task-1")
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        self.service.load_provenance_lineage_graph("param:0:exec-1:task-1", "chip-1", max_depth=99)

        _, kwargs = mock_service.get_lineage.call_args
        assert kwargs["max_depth"] == 20

    @patch.object(CopilotDataService, "_resolve_project_id", return_value="proj-1")
    @patch.object(CopilotDataService, "_get_provenance_service")
    def test_max_depth_clamped_to_lower_bound(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        """max_depth < 1 should be clamped to 1."""
        mock_service = MagicMock()
        mock_lineage = _make_empty_lineage("param:0:exec-1:task-1")
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        self.service.load_provenance_lineage_graph("param:0:exec-1:task-1", "chip-1", max_depth=-5)

        _, kwargs = mock_service.get_lineage.call_args
        assert kwargs["max_depth"] == 1


class TestProvenanceLineageGraphOutput:
    """Tests for the LLM-friendly output structure."""

    def setup_method(self):
        self.service = CopilotDataService()

    @patch.object(CopilotDataService, "_resolve_project_id", return_value="proj-1")
    @patch.object(CopilotDataService, "_get_provenance_service")
    def test_successful_lineage_returns_expected_structure(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        mock_service = MagicMock()
        mock_lineage = _make_lineage_with_entity_and_activity()
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        result = self.service.load_provenance_lineage_graph("qf:0:exec-1:task-1", "chip-1")

        assert "error" not in result
        assert result["origin"] == "qf:0:exec-1:task-1"
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)
        assert result["num_nodes"] == len(result["nodes"])
        assert result["num_edges"] == len(result["edges"])
        assert "max_depth" in result

    @patch.object(CopilotDataService, "_resolve_project_id", return_value="proj-1")
    @patch.object(CopilotDataService, "_get_provenance_service")
    def test_entity_node_has_parameter_fields(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        mock_service = MagicMock()
        mock_lineage = _make_lineage_with_entity_and_activity()
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        result = self.service.load_provenance_lineage_graph("qf:0:exec-1:task-1", "chip-1")

        entity_nodes = [n for n in result["nodes"] if n["type"] == "entity"]
        assert len(entity_nodes) >= 1
        node = entity_nodes[0]
        assert node["param"] is not None
        assert node["value"] is not None
        assert node["unit"] is not None
        assert node["ver"] is not None
        assert node["task"] is not None

    @patch.object(CopilotDataService, "_resolve_project_id", return_value="proj-1")
    @patch.object(CopilotDataService, "_get_provenance_service")
    def test_activity_node_has_task_fields(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        mock_service = MagicMock()
        mock_lineage = _make_lineage_with_entity_and_activity()
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        result = self.service.load_provenance_lineage_graph("qf:0:exec-1:task-1", "chip-1")

        activity_nodes = [n for n in result["nodes"] if n["type"] == "activity"]
        assert len(activity_nodes) >= 1
        node = activity_nodes[0]
        assert node["task"] is not None
        assert node["exec_id"] is not None
        assert node["status"] is not None

    @patch.object(CopilotDataService, "_resolve_project_id", return_value="proj-1")
    @patch.object(CopilotDataService, "_get_provenance_service")
    def test_latest_version_included_when_present(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        mock_service = MagicMock()
        mock_lineage = _make_lineage_with_entity_and_activity()
        # Set latest_version on the first node to simulate a stale input
        mock_lineage.nodes[0].latest_version = 5
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        result = self.service.load_provenance_lineage_graph("qf:0:exec-1:task-1", "chip-1")

        versions_with_latest = [
            n["ver"] for n in result["nodes"] if isinstance(n["ver"], str) and "/" in n["ver"]
        ]
        assert len(versions_with_latest) >= 1
        assert "5" in versions_with_latest[0]


class TestToolRegistration:
    """Tests that the new tool is properly registered everywhere."""

    def test_tool_in_agent_tools(self):
        names = [t["name"] for t in AGENT_TOOLS]
        assert "get_provenance_lineage_graph" in names

    def test_tool_definition_has_required_params(self):
        tool = next(t for t in AGENT_TOOLS if t["name"] == "get_provenance_lineage_graph")
        required = tool["parameters"]["required"]
        assert "entity_id" in required
        assert "chip_id" in required

    def test_tool_in_labels(self):
        assert "get_provenance_lineage_graph" in TOOL_LABELS

    def test_tool_in_executors(self):
        service = CopilotDataService()
        executors = service.build_tool_executors()
        assert "get_provenance_lineage_graph" in executors

    def test_execute_python_analysis_has_no_context_data_param(self):
        tool = next(t for t in AGENT_TOOLS if t["name"] == "execute_python_analysis")
        props = tool["parameters"]["properties"]
        assert "context_data" not in props
        assert "code" in props


class TestBuildLlmSummary:
    """Tests for _build_llm_summary."""

    def test_list_of_dicts_replaced_with_schema(self):
        full = {
            "chip_id": "chip-1",
            "qubits": [
                {"qid": "0", "latest": 5.05},
                {"qid": "1", "latest": 4.98},
            ],
        }
        summary = _build_llm_summary(full, "t1")
        assert summary["chip_id"] == "chip-1"
        assert summary["qubits"]["_schema"] == ["qid", "latest"]
        assert summary["qubits"]["_rows"] == 2
        assert summary["data_key"] == "t1"
        assert "data['t1']" in summary["_note"]

    def test_plain_list_replaced_with_row_count(self):
        full = {"values": [1, 2, 3]}
        summary = _build_llm_summary(full, "key")
        assert summary["values"]["_rows"] == 3
        assert "_schema" not in summary["values"]

    def test_scalar_values_preserved(self):
        full = {"chip_id": "chip-1", "num_qubits": 10, "unit": "GHz"}
        summary = _build_llm_summary(full, "key")
        assert summary["chip_id"] == "chip-1"
        assert summary["num_qubits"] == 10
        assert summary["unit"] == "GHz"

    def test_empty_list_replaced(self):
        full: dict[str, Any] = {"items": []}
        summary = _build_llm_summary(full, "key")
        assert summary["items"]["_rows"] == 0


class TestDataStoreWrapper:
    """Tests for _wrap_tool_executors data store behaviour."""

    def test_stored_tool_saves_to_data_store(self):
        data_store: dict[str, Any] = {}
        mock_result = {
            "chip_id": "chip-1",
            "parameter_name": "t1",
            "timeseries": [{"qid": "0", "v": 45.2, "t": "2026-01-01"}],
            "qubits": [{"qid": "0", "latest": 45.2}],
        }
        executors = {
            "get_chip_parameter_timeseries": lambda args: mock_result,
        }
        wrapped, _ = _wrap_tool_executors(executors, data_store)
        result = wrapped["get_chip_parameter_timeseries"]({"parameter_name": "t1"})

        # Full data stored
        assert "t1" in data_store
        assert data_store["t1"] is mock_result

        # LLM receives summary only
        assert result["data_key"] == "t1"
        assert result["timeseries"]["_rows"] == 1

    def test_stored_tool_error_not_saved(self):
        data_store: dict[str, Any] = {}
        executors = {
            "get_chip_parameter_timeseries": lambda args: {"error": "No data"},
        }
        wrapped, _ = _wrap_tool_executors(executors, data_store)
        result = wrapped["get_chip_parameter_timeseries"]({"parameter_name": "t1"})

        assert data_store == {}
        assert result["error"] == "No data"

    def test_chip_summary_uses_fixed_key(self):
        data_store: dict[str, Any] = {}
        mock_result = {"chip_id": "c", "qubits": [{"qid": "0"}], "statistics": {}}
        executors = {
            "get_chip_summary": lambda args: mock_result,
        }
        wrapped, _ = _wrap_tool_executors(executors, data_store)
        result = wrapped["get_chip_summary"]({"chip_id": "c"})

        assert "chip_summary" in data_store
        assert result["data_key"] == "chip_summary"

    def test_python_analysis_receives_data_store(self):
        data_store = {"t1": {"timeseries": [{"v": 45.2}]}}
        executors = {
            "execute_python_analysis": lambda args: None,  # overridden
        }
        wrapped, _ = _wrap_tool_executors(executors, data_store)

        # Call with code that accesses data
        result = wrapped["execute_python_analysis"](
            {"code": "result = {'output': str(data.get('t1', {})), 'chart': None}"}
        )
        assert result["error"] is None
        assert "timeseries" in result["output"]


# --------------- helpers ---------------


def _make_empty_lineage(origin_id: str) -> LineageResponse:
    """Create a minimal LineageResponse mock with no nodes/edges."""
    from qdash.api.schemas.provenance import LineageNodeResponse, LineageResponse

    origin = LineageNodeResponse(node_type="entity", node_id=origin_id, depth=0)
    return LineageResponse(origin=origin, nodes=[], edges=[], max_depth=5)


def _make_lineage_with_entity_and_activity() -> LineageResponse:
    """Create a LineageResponse with one entity node and one activity node."""
    from qdash.api.schemas.provenance import (
        ActivityResponse,
        LineageEdgeResponse,
        LineageNodeResponse,
        LineageResponse,
        ParameterVersionResponse,
    )

    entity_node = LineageNodeResponse(
        node_type="entity",
        node_id="qf:0:exec-1:task-1",
        depth=0,
        entity=ParameterVersionResponse(
            entity_id="qf:0:exec-1:task-1",
            parameter_name="qubit_frequency",
            qid="0",
            value=5.05,
            unit="GHz",
            version=2,
            valid_from=datetime(2025, 6, 1, 12, 0, 0),
            execution_id="exec-1",
            task_id="task-1",
            task_name="CheckQubitFrequency",
            project_id="proj-1",
            chip_id="chip-1",
        ),
        latest_version=None,
    )

    activity_node = LineageNodeResponse(
        node_type="activity",
        node_id="exec-1:task-1",
        depth=1,
        activity=ActivityResponse(
            activity_id="exec-1:task-1",
            execution_id="exec-1",
            task_id="task-1",
            task_name="CheckQubitFrequency",
            task_type="check",
            qid="0",
            status="completed",
            project_id="proj-1",
            chip_id="chip-1",
        ),
    )

    edge = LineageEdgeResponse(
        relation_type="wasGeneratedBy",
        source_id="qf:0:exec-1:task-1",
        target_id="exec-1:task-1",
    )

    origin = entity_node
    return LineageResponse(
        origin=origin,
        nodes=[entity_node, activity_node],
        edges=[edge],
        max_depth=5,
    )
