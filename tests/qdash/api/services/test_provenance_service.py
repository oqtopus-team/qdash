"""Tests for ProvenanceService."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from qdash.api.schemas.provenance import (
    ExecutionComparisonResponse,
    ImpactResponse,
    LineageResponse,
    ParameterHistoryResponse,
    ParameterVersionResponse,
    ProvenanceStatsResponse,
)
from qdash.api.services.provenance_service import ProvenanceService


class TestProvenanceService:
    """Tests for ProvenanceService business logic."""

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories."""
        return {
            "parameter_version": MagicMock(),
            "provenance_relation": MagicMock(),
            "activity": MagicMock(),
        }

    @pytest.fixture
    def service(self, mock_repos):
        """Create ProvenanceService with mock repositories."""
        return ProvenanceService(
            parameter_version_repo=mock_repos["parameter_version"],
            provenance_relation_repo=mock_repos["provenance_relation"],
            activity_repo=mock_repos["activity"],
        )

    def test_get_entity_returns_response_when_found(self, service, mock_repos):
        """Test get_entity returns ParameterVersionResponse when entity exists."""
        mock_entity = MagicMock()
        mock_entity.entity_id = "param:Q0:exec-001:task-001"
        mock_entity.parameter_name = "qubit_frequency"
        mock_entity.qid = "Q0"
        mock_entity.value = 5.0
        mock_entity.value_type = "float"
        mock_entity.unit = "GHz"
        mock_entity.error = 0.01
        mock_entity.version = 1
        mock_entity.valid_from = datetime(2025, 1, 1, 10, 0, 0)
        mock_entity.valid_until = None
        mock_entity.execution_id = "exec-001"
        mock_entity.task_id = "task-001"
        mock_entity.task_name = "CheckQubit"
        mock_entity.project_id = "test_project"
        mock_entity.chip_id = "chip-001"

        mock_repos["parameter_version"].get_by_entity_id.return_value = mock_entity

        result = service.get_entity("test_project", "param:Q0:exec-001:task-001")

        assert result is not None
        assert isinstance(result, ParameterVersionResponse)
        assert result.entity_id == "param:Q0:exec-001:task-001"
        assert result.parameter_name == "qubit_frequency"
        assert result.value == 5.0

    def test_get_entity_returns_none_when_not_found(self, service, mock_repos):
        """Test get_entity returns None when entity doesn't exist."""
        mock_repos["parameter_version"].get_by_entity_id.return_value = None

        result = service.get_entity("test_project", "nonexistent:entity")

        assert result is None

    def test_get_entity_returns_none_for_wrong_project(self, service, mock_repos):
        """Test get_entity returns None when entity belongs to different project."""
        mock_entity = MagicMock()
        mock_entity.project_id = "other_project"

        mock_repos["parameter_version"].get_by_entity_id.return_value = mock_entity

        result = service.get_entity("test_project", "param:Q0:exec-001:task-001")

        assert result is None

    def test_get_lineage_returns_response(self, service, mock_repos):
        """Test get_lineage returns LineageResponse."""
        mock_repos["provenance_relation"].get_lineage.return_value = {
            "nodes": [
                {
                    "id": "param:Q0:exec-001:task-001",
                    "type": "entity",
                    "metadata": {
                        "parameter_name": "qubit_frequency",
                        "qid": "Q0",
                        "value": 5.0,
                        "version": 1,
                    },
                }
            ],
            "edges": [],
        }

        result = service.get_lineage("test_project", "param:Q0:exec-001:task-001")

        assert isinstance(result, LineageResponse)
        assert result.max_depth == 10
        assert len(result.nodes) == 1
        assert result.origin.node_id == "param:Q0:exec-001:task-001"

    def test_get_lineage_with_custom_depth(self, service, mock_repos):
        """Test get_lineage respects max_depth parameter."""
        mock_repos["provenance_relation"].get_lineage.return_value = {
            "nodes": [],
            "edges": [],
        }

        result = service.get_lineage("test_project", "param:Q0:exec-001:task-001", max_depth=5)

        assert result.max_depth == 5
        mock_repos["provenance_relation"].get_lineage.assert_called_once_with(
            project_id="test_project",
            entity_id="param:Q0:exec-001:task-001",
            max_depth=5,
        )

    def test_get_lineage_converts_edges(self, service, mock_repos):
        """Test get_lineage properly converts edge data."""
        mock_repos["provenance_relation"].get_lineage.return_value = {
            "nodes": [
                {"id": "entity1", "type": "entity", "metadata": {}},
                {"id": "activity1", "type": "activity", "metadata": {}},
            ],
            "edges": [
                {
                    "source": "entity1",
                    "target": "activity1",
                    "relation_type": "wasGeneratedBy",
                }
            ],
        }

        result = service.get_lineage("test_project", "entity1")

        assert len(result.edges) == 1
        assert result.edges[0].source_id == "entity1"
        assert result.edges[0].target_id == "activity1"
        assert result.edges[0].relation_type == "wasGeneratedBy"

    def test_get_impact_returns_response(self, service, mock_repos):
        """Test get_impact returns ImpactResponse."""
        mock_repos["provenance_relation"].get_impact.return_value = {
            "nodes": [
                {
                    "id": "param:Q0:exec-001:task-001",
                    "type": "entity",
                    "metadata": {},
                }
            ],
            "edges": [],
        }

        result = service.get_impact("test_project", "param:Q0:exec-001:task-001")

        assert isinstance(result, ImpactResponse)
        assert result.max_depth == 10
        assert len(result.nodes) == 1

    def test_get_impact_with_custom_depth(self, service, mock_repos):
        """Test get_impact respects max_depth parameter."""
        mock_repos["provenance_relation"].get_impact.return_value = {
            "nodes": [],
            "edges": [],
        }

        result = service.get_impact("test_project", "param:Q0:exec-001:task-001", max_depth=3)

        assert result.max_depth == 3
        mock_repos["provenance_relation"].get_impact.assert_called_once_with(
            project_id="test_project",
            entity_id="param:Q0:exec-001:task-001",
            max_depth=3,
        )

    def test_compare_executions_returns_response(self, service, mock_repos):
        """Test compare_executions returns ExecutionComparisonResponse."""
        mock_repos["provenance_relation"].compare_executions.return_value = [
            {
                "change_type": "changed",
                "parameter_name": "qubit_frequency",
                "qid": "Q0",
                "before": {"value": 5.0},
                "after": {"value": 5.1},
            },
            {
                "change_type": "added",
                "parameter_name": "rabi_frequency",
                "qid": "Q0",
                "before": None,
                "after": {"value": 50.0},
            },
        ]

        result = service.compare_executions("test_project", "exec-001", "exec-002")

        assert isinstance(result, ExecutionComparisonResponse)
        assert result.execution_id_before == "exec-001"
        assert result.execution_id_after == "exec-002"
        assert len(result.changed_parameters) == 1
        assert len(result.added_parameters) == 1
        assert len(result.removed_parameters) == 0

    def test_compare_executions_calculates_delta(self, service, mock_repos):
        """Test compare_executions calculates numeric deltas."""
        mock_repos["provenance_relation"].compare_executions.return_value = [
            {
                "change_type": "changed",
                "parameter_name": "qubit_frequency",
                "qid": "Q0",
                "before": {"value": 5.0},
                "after": {"value": 5.5},
            }
        ]

        result = service.compare_executions("test_project", "exec-001", "exec-002")

        assert len(result.changed_parameters) == 1
        changed = result.changed_parameters[0]
        assert changed.delta == 0.5
        assert changed.delta_percent == 10.0

    def test_compare_executions_handles_removed(self, service, mock_repos):
        """Test compare_executions handles removed parameters."""
        mock_repos["provenance_relation"].compare_executions.return_value = [
            {
                "change_type": "removed",
                "parameter_name": "old_param",
                "qid": "Q0",
                "before": {"value": 1.0},
                "after": None,
            }
        ]

        result = service.compare_executions("test_project", "exec-001", "exec-002")

        assert len(result.removed_parameters) == 1
        assert result.removed_parameters[0].parameter_name == "old_param"
        assert result.removed_parameters[0].value_before == 1.0
        assert result.removed_parameters[0].value_after is None

    def test_get_parameter_history_returns_response(self, service, mock_repos):
        """Test get_parameter_history returns ParameterHistoryResponse."""
        mock_versions = [
            MagicMock(
                entity_id="param:Q0:exec-002:task-001",
                parameter_name="qubit_frequency",
                qid="Q0",
                value=5.2,
                value_type="float",
                unit="GHz",
                error=0.01,
                version=3,
                valid_from=datetime(2025, 1, 1, 12, 0, 0),
                valid_until=None,
                execution_id="exec-002",
                task_id="task-001",
                task_name="CheckQubit",
                project_id="test_project",
                chip_id="chip-001",
            ),
            MagicMock(
                entity_id="param:Q0:exec-001:task-001",
                parameter_name="qubit_frequency",
                qid="Q0",
                value=5.1,
                value_type="float",
                unit="GHz",
                error=0.01,
                version=2,
                valid_from=datetime(2025, 1, 1, 11, 0, 0),
                valid_until=datetime(2025, 1, 1, 12, 0, 0),
                execution_id="exec-001",
                task_id="task-001",
                task_name="CheckQubit",
                project_id="test_project",
                chip_id="chip-001",
            ),
        ]

        mock_repos["parameter_version"].get_version_history.return_value = mock_versions

        result = service.get_parameter_history("test_project", "qubit_frequency", "Q0")

        assert isinstance(result, ParameterHistoryResponse)
        assert result.parameter_name == "qubit_frequency"
        assert result.qid == "Q0"
        assert result.total_versions == 2
        assert len(result.versions) == 2
        assert result.versions[0].version == 3  # Newest first

    def test_get_parameter_history_with_limit(self, service, mock_repos):
        """Test get_parameter_history respects limit parameter."""
        mock_repos["parameter_version"].get_version_history.return_value = []

        service.get_parameter_history("test_project", "qubit_frequency", "Q0", limit=10)

        mock_repos["parameter_version"].get_version_history.assert_called_once_with(
            project_id="test_project",
            parameter_name="qubit_frequency",
            qid="Q0",
            limit=10,
        )

    def test_get_parameter_history_empty(self, service, mock_repos):
        """Test get_parameter_history returns empty response for no versions."""
        mock_repos["parameter_version"].get_version_history.return_value = []

        result = service.get_parameter_history("test_project", "nonexistent", "Q0")

        assert result.versions == []
        assert result.total_versions == 0

    def test_get_stats_returns_response(self, service, mock_repos):
        """Test get_stats returns ProvenanceStatsResponse."""
        # Set up mock return values for the new repository methods
        mock_repos["parameter_version"].count.return_value = 10
        mock_repos["parameter_version"].get_recent.return_value = []
        mock_repos["activity"].count.return_value = 5
        mock_repos["provenance_relation"].count.return_value = 20
        mock_repos["provenance_relation"].count_by_type.return_value = {
            "wasGeneratedBy": 10,
            "wasDerivedFrom": 10,
        }

        result = service.get_stats("test_project")

        assert isinstance(result, ProvenanceStatsResponse)
        assert result.total_entities == 10
        assert result.total_activities == 5
        assert result.total_relations == 20
        assert result.relation_counts == {"wasGeneratedBy": 10, "wasDerivedFrom": 10}
        assert result.recent_entities == []

    def test_build_version_response_from_dict(self, service):
        """Test _build_version_response handles dict input."""
        entity_dict = {
            "entity_id": "param:Q0:exec-001:task-001",
            "parameter_name": "qubit_frequency",
            "qid": "Q0",
            "value": 5.0,
            "value_type": "float",
            "unit": "GHz",
            "error": 0.01,
            "version": 1,
            "valid_from": datetime(2025, 1, 1, 10, 0, 0),
            "valid_until": None,
            "execution_id": "exec-001",
            "task_id": "task-001",
            "task_name": "CheckQubit",
            "project_id": "test_project",
            "chip_id": "chip-001",
        }

        result = service._build_version_response(entity_dict)

        assert isinstance(result, ParameterVersionResponse)
        assert result.entity_id == "param:Q0:exec-001:task-001"
        assert result.parameter_name == "qubit_frequency"
        assert result.value == 5.0

    def test_build_version_from_metadata_returns_none_for_empty(self, service):
        """Test _build_version_from_metadata returns None for empty metadata."""
        result = service._build_version_from_metadata({"id": "test", "metadata": {}})

        assert result is None

    def test_build_version_from_metadata_with_data(self, service):
        """Test _build_version_from_metadata creates response from metadata."""
        item = {
            "id": "param:Q0:exec-001:task-001",
            "type": "entity",
            "metadata": {
                "parameter_name": "qubit_frequency",
                "qid": "Q0",
                "value": 5.0,
                "version": 1,
                "unit": "GHz",
                "task_name": "CheckQubit",
            },
        }

        result = service._build_version_from_metadata(item)

        assert result is not None
        assert isinstance(result, ParameterVersionResponse)
        assert result.entity_id == "param:Q0:exec-001:task-001"
        assert result.parameter_name == "qubit_frequency"

    def test_build_activity_from_metadata_returns_none_for_empty(self, service):
        """Test _build_activity_from_metadata returns None for empty metadata."""
        result = service._build_activity_from_metadata({"id": "test", "metadata": {}})

        assert result is None

    def test_build_activity_from_metadata_with_data(self, service):
        """Test _build_activity_from_metadata creates response from metadata."""
        item = {
            "id": "exec-001:task-001",
            "type": "activity",
            "metadata": {
                "task_name": "CheckQubit",
                "qid": "Q0",
                "status": "completed",
            },
        }

        result = service._build_activity_from_metadata(item)

        assert result is not None
        assert result.activity_id == "exec-001:task-001"
        assert result.task_name == "CheckQubit"
        assert result.status == "completed"
