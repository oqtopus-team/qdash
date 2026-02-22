"""Tests for copilot provenance lineage graph tool."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from qdash.api.lib.copilot_agent import AGENT_TOOLS
from qdash.api.routers.copilot import (
    TOOL_LABELS,
    _build_tool_executors,
    _load_provenance_lineage_graph,
)


class TestProvenanceLineageGraphValidation:
    """Tests for entity_id format validation and max_depth bounds."""

    def test_empty_entity_id_returns_error(self):
        result = _load_provenance_lineage_graph("", "chip-1")
        assert "error" in result
        assert "Invalid entity_id format" in result["error"]

    def test_entity_id_too_few_colons_returns_error(self):
        result = _load_provenance_lineage_graph("param:qid", "chip-1")
        assert "error" in result
        assert "Invalid entity_id format" in result["error"]

    def test_entity_id_too_many_colons_returns_error(self):
        result = _load_provenance_lineage_graph("a:b:c:d:e", "chip-1")
        assert "error" in result
        assert "Invalid entity_id format" in result["error"]

    @patch("qdash.api.routers.copilot._resolve_project_id", return_value=None)
    def test_missing_chip_returns_descriptive_error(self, _mock_resolve):
        result = _load_provenance_lineage_graph("param:0:exec-1:task-1", "nonexistent-chip")
        assert "error" in result
        assert "nonexistent-chip" in result["error"]
        assert "may not exist" in result["error"]

    @patch("qdash.api.routers.copilot._resolve_project_id", return_value="proj-1")
    @patch("qdash.api.routers.copilot._get_provenance_service")
    def test_max_depth_clamped_to_upper_bound(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        """max_depth > 20 should be clamped to 20."""
        mock_service = MagicMock()
        mock_lineage = _make_empty_lineage("param:0:exec-1:task-1")
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        _load_provenance_lineage_graph("param:0:exec-1:task-1", "chip-1", max_depth=99)

        _, kwargs = mock_service.get_lineage.call_args
        assert kwargs["max_depth"] == 20

    @patch("qdash.api.routers.copilot._resolve_project_id", return_value="proj-1")
    @patch("qdash.api.routers.copilot._get_provenance_service")
    def test_max_depth_clamped_to_lower_bound(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        """max_depth < 1 should be clamped to 1."""
        mock_service = MagicMock()
        mock_lineage = _make_empty_lineage("param:0:exec-1:task-1")
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        _load_provenance_lineage_graph("param:0:exec-1:task-1", "chip-1", max_depth=-5)

        _, kwargs = mock_service.get_lineage.call_args
        assert kwargs["max_depth"] == 1


class TestProvenanceLineageGraphOutput:
    """Tests for the LLM-friendly output structure."""

    @patch("qdash.api.routers.copilot._resolve_project_id", return_value="proj-1")
    @patch("qdash.api.routers.copilot._get_provenance_service")
    def test_successful_lineage_returns_expected_structure(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        mock_service = MagicMock()
        mock_lineage = _make_lineage_with_entity_and_activity()
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        result = _load_provenance_lineage_graph("qf:0:exec-1:task-1", "chip-1")

        assert "error" not in result
        assert result["origin"] == "qf:0:exec-1:task-1"
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)
        assert result["num_nodes"] == len(result["nodes"])
        assert result["num_edges"] == len(result["edges"])
        assert "max_depth" in result

    @patch("qdash.api.routers.copilot._resolve_project_id", return_value="proj-1")
    @patch("qdash.api.routers.copilot._get_provenance_service")
    def test_entity_node_has_parameter_fields(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        mock_service = MagicMock()
        mock_lineage = _make_lineage_with_entity_and_activity()
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        result = _load_provenance_lineage_graph("qf:0:exec-1:task-1", "chip-1")

        entity_nodes = [n for n in result["nodes"] if n["node_type"] == "entity"]
        assert len(entity_nodes) >= 1
        node = entity_nodes[0]
        assert "parameter_name" in node
        assert "value" in node
        assert "unit" in node
        assert "version" in node
        assert "task_name" in node

    @patch("qdash.api.routers.copilot._resolve_project_id", return_value="proj-1")
    @patch("qdash.api.routers.copilot._get_provenance_service")
    def test_activity_node_has_task_fields(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        mock_service = MagicMock()
        mock_lineage = _make_lineage_with_entity_and_activity()
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        result = _load_provenance_lineage_graph("qf:0:exec-1:task-1", "chip-1")

        activity_nodes = [n for n in result["nodes"] if n["node_type"] == "activity"]
        assert len(activity_nodes) >= 1
        node = activity_nodes[0]
        assert "task_name" in node
        assert "execution_id" in node
        assert "status" in node

    @patch("qdash.api.routers.copilot._resolve_project_id", return_value="proj-1")
    @patch("qdash.api.routers.copilot._get_provenance_service")
    def test_latest_version_included_when_present(
        self, mock_get_service: MagicMock, _mock_resolve: MagicMock
    ):
        mock_service = MagicMock()
        mock_lineage = _make_lineage_with_entity_and_activity()
        # Set latest_version on the first node to simulate a stale input
        mock_lineage.nodes[0].latest_version = 5
        mock_service.get_lineage.return_value = mock_lineage
        mock_get_service.return_value = mock_service

        result = _load_provenance_lineage_graph("qf:0:exec-1:task-1", "chip-1")

        nodes_with_latest = [n for n in result["nodes"] if "latest_version" in n]
        assert len(nodes_with_latest) >= 1
        assert nodes_with_latest[0]["latest_version"] == 5


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
        executors = _build_tool_executors()
        assert "get_provenance_lineage_graph" in executors


# --------------- helpers ---------------


def _make_empty_lineage(origin_id: str) -> MagicMock:
    """Create a minimal LineageResponse mock with no nodes/edges."""
    from qdash.api.schemas.provenance import LineageNodeResponse, LineageResponse

    origin = LineageNodeResponse(node_type="entity", node_id=origin_id, depth=0)
    return LineageResponse(origin=origin, nodes=[], edges=[], max_depth=5)


def _make_lineage_with_entity_and_activity() -> MagicMock:
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
