"""Tests for ProvenanceService."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from qdash.api.schemas.provenance import (
    DegradationTrendsResponse,
    ExecutionComparisonResponse,
    ImpactResponse,
    LineageResponse,
    ParameterHistoryResponse,
    ParameterVersionResponse,
    ProvenanceStatsResponse,
    RecalibrationRecommendationResponse,
    RecentChangesResponse,
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

    def test_get_recalibration_recommendations_groups_tasks_by_depth(self, service, mock_repos):
        """Impact graph nodes are grouped per task and sorted by minimum depth."""
        source_entity = MagicMock()
        source_entity.parameter_name = "qubit_frequency"
        source_entity.qid = "Q0"
        mock_repos["parameter_version"].get_by_entity_id.return_value = source_entity
        mock_repos["provenance_relation"].get_impact.return_value = {
            "nodes": [
                {
                    "id": "source",
                    "type": "entity",
                    "metadata": {"parameter_name": "qubit_frequency", "qid": "Q0"},
                },
                {
                    "id": "task-rabi",
                    "type": "activity",
                    "metadata": {"task_name": "CheckRabi", "qid": "Q0"},
                },
                {
                    "id": "entity-rabi",
                    "type": "entity",
                    "metadata": {
                        "task_name": "CheckRabi",
                        "parameter_name": "rabi_amplitude",
                        "qid": "Q0",
                    },
                },
                {
                    "id": "task-t1",
                    "type": "activity",
                    "metadata": {"task_name": "CheckT1", "qid": "Q1"},
                },
                {
                    "id": "entity-t1",
                    "type": "entity",
                    "metadata": {
                        "task_name": "CheckT1",
                        "parameter_name": "t1",
                        "qid": "Q1",
                    },
                },
            ],
            "edges": [
                {"relation_type": "used", "source": "task-rabi", "target": "source"},
                {"relation_type": "generated", "source": "entity-rabi", "target": "task-rabi"},
                {"relation_type": "used", "source": "task-t1", "target": "entity-rabi"},
                {"relation_type": "generated", "source": "entity-t1", "target": "task-t1"},
            ],
        }

        result = service.get_recalibration_recommendations("proj", "source")

        assert isinstance(result, RecalibrationRecommendationResponse)
        assert result.source_parameter_name == "qubit_frequency"
        assert result.source_qid == "Q0"
        assert result.total_affected_parameters == 2
        assert result.max_depth_reached == 4
        assert [task.task_name for task in result.recommended_tasks] == ["CheckRabi", "CheckT1"]
        assert [task.priority for task in result.recommended_tasks] == [1, 2]
        assert result.recommended_tasks[0].affected_parameters == ["rabi_amplitude"]
        assert result.recommended_tasks[0].affected_qids == ["Q0"]
        assert "triggered by qubit_frequency (Q0) change" in result.recommended_tasks[0].reason
        assert "e.g., rabi_amplitude (Q0) at depth=2" in result.recommended_tasks[0].reason

    def test_get_recalibration_recommendations_handles_missing_source_entity(
        self, service, mock_repos
    ):
        """Recommendations still build when the source entity is unavailable."""
        mock_repos["parameter_version"].get_by_entity_id.return_value = None
        mock_repos["provenance_relation"].get_impact.return_value = {
            "nodes": [
                {
                    "id": "task-rabi",
                    "type": "activity",
                    "metadata": {"task_name": "CheckRabi", "qid": "Q0"},
                },
                {
                    "id": "entity-rabi",
                    "type": "entity",
                    "metadata": {
                        "task_name": "CheckRabi",
                        "parameter_name": "rabi_amplitude",
                        "qid": "Q0",
                    },
                },
            ],
            "edges": [
                {"relation_type": "used", "source": "task-rabi", "target": "source"},
                {"relation_type": "generated", "source": "entity-rabi", "target": "task-rabi"},
            ],
        }

        result = service.get_recalibration_recommendations("proj", "source")

        assert result.source_parameter_name == ""
        assert result.source_qid == ""
        assert result.recommended_tasks[0].task_name == "CheckRabi"
        assert "triggered by" not in result.recommended_tasks[0].reason

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
        assert result.changed_parameters[0].delta == pytest.approx(0.1)
        assert result.changed_parameters[0].delta_percent == pytest.approx(2.0)
        assert result.added_parameters[0].delta is None

    def test_compare_executions_ignores_non_numeric_delta(self, service, mock_repos):
        """Changed parameters without numeric values keep delta fields empty."""
        mock_repos["provenance_relation"].compare_executions.return_value = [
            {
                "change_type": "changed",
                "parameter_name": "label",
                "qid": "Q0",
                "before": {"value": "idle"},
                "after": {"value": "active"},
            }
        ]

        result = service.compare_executions("test_project", "exec-001", "exec-002")

        assert result.changed_parameters[0].delta is None
        assert result.changed_parameters[0].delta_percent is None

    def test_get_recent_changes_builds_delta_from_previous_version(self, service, mock_repos):
        """Recent changes include delta metadata from the previous version."""
        current = MagicMock()
        current.entity_id = "param:Q0:e2:t2"
        current.parameter_name = "t1"
        current.qid = "Q0"
        current.value = 8.0
        current.unit = "us"
        current.error = 0.2
        current.version = 2
        current.valid_from = datetime(2025, 1, 2, 10, 0, 0)
        current.task_name = "CheckT1"
        current.execution_id = "exec-002"

        previous = MagicMock()
        previous.value = 10.0
        previous.error = 0.1

        mock_repos["parameter_version"].get_recent.return_value = [current]
        mock_repos["parameter_version"].get_version.return_value = previous

        result = service.get_recent_changes("test_project", limit=5)

        assert isinstance(result, RecentChangesResponse)
        assert result.total_count == 1
        change = result.changes[0]
        assert change.parameter_name == "t1"
        assert change.delta == pytest.approx(-2.0)
        assert change.delta_percent == pytest.approx(-20.0)
        assert change.previous_value == 10.0
        assert change.previous_error == pytest.approx(0.1)

    def test_get_recent_changes_filters_and_skips_version_one(self, service, mock_repos):
        """Parameter filters apply before diffing, and version 1 documents are ignored."""
        skipped = MagicMock()
        skipped.parameter_name = "t1"
        skipped.version = 1

        filtered = MagicMock()
        filtered.parameter_name = "qubit_frequency"
        filtered.version = 3

        kept = MagicMock()
        kept.entity_id = "param:Q0:e3:t3"
        kept.parameter_name = "t1"
        kept.qid = "Q0"
        kept.value = 4.0
        kept.unit = "us"
        kept.error = 0.0
        kept.version = 3
        kept.valid_from = datetime(2025, 1, 3, 10, 0, 0)
        kept.task_name = "CheckT1"
        kept.execution_id = "exec-003"

        previous = MagicMock()
        previous.value = 2.0
        previous.error = 0.0

        mock_repos["parameter_version"].get_recent.return_value = [skipped, filtered, kept]
        mock_repos["parameter_version"].get_version.return_value = previous

        result = service.get_recent_changes(
            "test_project",
            limit=5,
            parameter_names=["t1"],
        )

        assert result.total_count == 1
        assert result.changes[0].entity_id == "param:Q0:e3:t3"
        mock_repos["parameter_version"].get_version.assert_called_once_with(
            project_id="test_project",
            parameter_name="t1",
            qid="Q0",
            version=2,
        )

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


class TestGetDegradationTrends:
    """Tests for ProvenanceService.get_degradation_trends."""

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

    @pytest.fixture
    def _mock_metrics(self, monkeypatch):
        """Mock load_metrics_config with maximize t1 and minimize qubit_frequency."""

        class _Eval:
            def __init__(self, mode):
                self.mode = mode

        class _Meta:
            def __init__(self, mode, unit=""):
                self.evaluation = _Eval(mode)
                self.unit = unit

        class _Config:
            qubit_metrics = {
                "t1": _Meta("maximize", "us"),
                "qubit_frequency": _Meta("minimize", "GHz"),
            }
            coupling_metrics = {}

        monkeypatch.setattr(
            "qdash.api.services.provenance_service.load_metrics_config",
            _Config,
        )

    def _make_versions(self, values, *, base_entity_id="param:Q0:exec", base_version=1):
        """Build a newest-first list of version dicts from a list of values."""
        versions = []
        for i, v in enumerate(values):
            versions.append(
                {
                    "version": base_version + len(values) - 1 - i,
                    "value": v,
                    "unit": "us",
                    "error": 0.0,
                    "entity_id": f"{base_entity_id}-{len(values) - 1 - i}:task",
                    "valid_from": datetime(2025, 1, 1, 10 + i, 0, 0),
                    "valid_until": None,
                }
            )
        return versions

    def test_maximize_streak_detected(self, service, mock_repos, _mock_metrics):
        """Maximize param with consecutive decreases → streak detected."""
        # newest first: 3, 4, 5, 6, 7  → 4 consecutive decreases
        versions = self._make_versions([3, 4, 5, 6, 7])
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = [
            {"parameter_name": "t1", "qid": "Q0", "versions": versions},
        ]

        result = service.get_degradation_trends("proj", min_streak=3)

        assert isinstance(result, DegradationTrendsResponse)
        assert len(result.trends) == 1
        trend = result.trends[0]
        assert trend.parameter_name == "t1"
        assert trend.streak_count == 4
        assert trend.total_delta == pytest.approx(3.0 - 7.0)
        assert trend.total_delta_percent == pytest.approx((3.0 - 7.0) / 7.0 * 100)
        assert trend.evaluation_mode == "maximize"

    def test_minimize_streak_detected(self, service, mock_repos, _mock_metrics):
        """Minimize param with consecutive increases → streak detected."""
        # newest first: 7, 6, 5, 4, 3  → 4 consecutive increases (worsening for minimize)
        versions = self._make_versions([7, 6, 5, 4, 3])
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = [
            {"parameter_name": "qubit_frequency", "qid": "Q0", "versions": versions},
        ]

        result = service.get_degradation_trends("proj", min_streak=3)

        assert len(result.trends) == 1
        trend = result.trends[0]
        assert trend.parameter_name == "qubit_frequency"
        assert trend.streak_count == 4
        assert trend.evaluation_mode == "minimize"

    def test_parameter_names_filter(self, service, mock_repos, _mock_metrics):
        """Only requested parameter_names are passed to the repository."""
        versions_t1 = self._make_versions([3, 4, 5, 6, 7])
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = [
            {"parameter_name": "t1", "qid": "Q0", "versions": versions_t1},
        ]

        result = service.get_degradation_trends("proj", min_streak=3, parameter_names=["t1"])

        # Repo should be called with only ["t1"]
        call_kwargs = mock_repos["parameter_version"].get_recent_versions_bulk.call_args
        assert call_kwargs[1]["parameter_names"] == ["t1"]
        # And result contains only t1
        assert len(result.trends) == 1
        assert result.trends[0].parameter_name == "t1"

    def test_parameter_names_filter_excludes_no_eval_mode(self, service, mock_repos, _mock_metrics):
        """Parameters not in eval_modes are excluded even if requested."""
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = []

        # "unknown_param" is not in metrics config → filtered out, empty result
        result = service.get_degradation_trends(
            "proj", min_streak=3, parameter_names=["unknown_param"]
        )

        assert result.trends == []
        assert result.total_count == 0

    def test_streak_below_min_streak_returns_empty(self, service, mock_repos, _mock_metrics):
        """When streak < min_streak, trends list is empty."""
        # streak = 2 (3 values: 4, 5, 6 → 2 decreases), but min_streak=3
        versions = self._make_versions([4, 5, 6])
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = [
            {"parameter_name": "t1", "qid": "Q0", "versions": versions},
        ]

        result = service.get_degradation_trends("proj", min_streak=3)

        assert result.trends == []
        assert result.total_count == 0

    def test_single_version_skipped(self, service, mock_repos, _mock_metrics):
        """Only 1 version → skipped (need at least 2)."""
        versions = self._make_versions([5])
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = [
            {"parameter_name": "t1", "qid": "Q0", "versions": versions},
        ]

        result = service.get_degradation_trends("proj", min_streak=3)

        assert result.trends == []

    def test_zero_versions_skipped(self, service, mock_repos, _mock_metrics):
        """Zero versions → skipped."""
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = [
            {"parameter_name": "t1", "qid": "Q0", "versions": []},
        ]

        result = service.get_degradation_trends("proj", min_streak=3)

        assert result.trends == []

    def test_non_numeric_value_streak_zero(self, service, mock_repos, _mock_metrics):
        """Non-numeric values break the streak → 0."""
        versions = self._make_versions(["bad", "also_bad", "nope", "still_bad"])
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = [
            {"parameter_name": "t1", "qid": "Q0", "versions": versions},
        ]

        result = service.get_degradation_trends("proj", min_streak=3)

        assert result.trends == []

    def test_sort_order_streak_then_delta_percent(self, service, mock_repos, _mock_metrics):
        """Trends sorted by streak desc, then |delta_percent| desc."""
        # t1: streak=4, delta from 7→3 = -57%
        versions_t1 = self._make_versions([3, 4, 5, 6, 7])
        # qubit_frequency: streak=4, delta from 3→7 = +133%
        versions_qf = self._make_versions([7, 6, 5, 4, 3])
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = [
            {"parameter_name": "t1", "qid": "Q0", "versions": versions_t1},
            {"parameter_name": "qubit_frequency", "qid": "Q0", "versions": versions_qf},
        ]

        result = service.get_degradation_trends("proj", min_streak=3)

        assert len(result.trends) == 2
        # Both streak=4, so sorted by |delta_percent| desc
        # qubit_frequency: |(7-3)/3*100| = 133.3  >  t1: |(3-7)/7*100| = 57.1
        assert result.trends[0].parameter_name == "qubit_frequency"
        assert result.trends[1].parameter_name == "t1"

    def test_repo_key_type_error_returns_empty(self, service, mock_repos, _mock_metrics):
        """KeyError/TypeError/ValueError → empty response + warning."""
        mock_repos["parameter_version"].get_recent_versions_bulk.side_effect = TypeError("bad type")

        result = service.get_degradation_trends("proj", min_streak=3)

        assert isinstance(result, DegradationTrendsResponse)
        assert result.trends == []
        assert result.total_count == 0

    def test_unexpected_exception_re_raised(self, service, mock_repos, _mock_metrics):
        """Non-computation errors are re-raised."""
        mock_repos["parameter_version"].get_recent_versions_bulk.side_effect = RuntimeError(
            "db down"
        )

        with pytest.raises(RuntimeError, match="db down"):
            service.get_degradation_trends("proj", min_streak=3)

    def test_limit_truncates_trends(self, service, mock_repos, _mock_metrics):
        """When more trends than limit, result is truncated."""
        # Create 3 separate (param, qid) combos that each have streak=4
        bulk = []
        for i in range(3):
            versions = self._make_versions([3, 4, 5, 6, 7])
            bulk.append({"parameter_name": "t1", "qid": f"Q{i}", "versions": versions})
        mock_repos["parameter_version"].get_recent_versions_bulk.return_value = bulk

        result = service.get_degradation_trends("proj", min_streak=3, limit=2)

        assert len(result.trends) == 2
        assert result.total_count == 3
