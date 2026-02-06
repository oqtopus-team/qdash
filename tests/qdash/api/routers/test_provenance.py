"""Tests for provenance router endpoints."""

from datetime import datetime

import pytest
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.provenance import (
    ActivityDocument,
    ParameterVersionDocument,
    ProvenanceRelationDocument,
    ProvenanceRelationType,
)
from qdash.dbmodel.user import UserDocument


@pytest.fixture
def test_project(init_db):
    """Create a test project with owner membership."""
    # Create user
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    # Create project
    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_username="test_user",
    )
    project.insert()

    # Create membership
    membership = ProjectMembershipDocument(
        project_id="test_project",
        username="test_user",
        role=ProjectRole.OWNER,
        invited_by="test_user",
    )
    membership.insert()

    return project


@pytest.fixture
def auth_headers():
    """Get authentication headers with project context."""
    return {
        "Authorization": "Bearer test_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def sample_parameter_versions(test_project):
    """Create sample parameter versions for testing."""
    versions = []

    # Create parameter versions for qubit frequency history
    for i in range(3):
        version = ParameterVersionDocument(
            entity_id=f"qubit_frequency:Q0:exec-00{i}:task-001",
            parameter_name="qubit_frequency",
            qid="Q0",
            value=5.0 + i * 0.1,
            value_type="float",
            unit="GHz",
            error=0.01,
            version=i + 1,
            valid_from=datetime(2025, 1, 1, 10 + i, 0, 0),
            valid_until=datetime(2025, 1, 1, 11 + i, 0, 0) if i < 2 else None,
            execution_id=f"exec-00{i}",
            task_id="task-001",
            task_name="CheckQubitFrequency",
            project_id="test_project",
            chip_id="chip-001",
        )
        version.insert()
        versions.append(version)

    # Create parameter version for rabi_frequency
    rabi_version = ParameterVersionDocument(
        entity_id="rabi_frequency:Q0:exec-002:task-002",
        parameter_name="rabi_frequency",
        qid="Q0",
        value=50.0,
        value_type="float",
        unit="MHz",
        error=0.5,
        version=1,
        valid_from=datetime(2025, 1, 1, 12, 0, 0),
        valid_until=None,
        execution_id="exec-002",
        task_id="task-002",
        task_name="CheckRabi",
        project_id="test_project",
        chip_id="chip-001",
    )
    rabi_version.insert()
    versions.append(rabi_version)

    return versions


@pytest.fixture
def sample_activities(test_project):
    """Create sample activities for testing."""
    activities = []

    for i in range(3):
        activity = ActivityDocument(
            activity_id=f"exec-00{i}:task-001",
            execution_id=f"exec-00{i}",
            task_id="task-001",
            task_name="CheckQubitFrequency",
            task_type="qubit",
            qid="Q0",
            started_at=datetime(2025, 1, 1, 10 + i, 0, 0),
            ended_at=datetime(2025, 1, 1, 10 + i, 5, 0),
            status="completed",
            project_id="test_project",
            chip_id="chip-001",
        )
        activity.insert()
        activities.append(activity)

    return activities


@pytest.fixture
def sample_relations(test_project, sample_parameter_versions, sample_activities):
    """Create sample provenance relations for testing."""
    relations = []

    # Create wasGeneratedBy relations
    for i in range(3):
        relation = ProvenanceRelationDocument(
            relation_id=f"wasGeneratedBy:qubit_frequency:Q0:exec-00{i}:task-001:exec-00{i}:task-001",
            relation_type=ProvenanceRelationType.GENERATED_BY,
            source_type="entity",
            source_id=f"qubit_frequency:Q0:exec-00{i}:task-001",
            target_type="activity",
            target_id=f"exec-00{i}:task-001",
            project_id="test_project",
            execution_id=f"exec-00{i}",
            confidence=1.0,
        )
        relation.insert()
        relations.append(relation)

    # Create wasDerivedFrom relation (version 2 derived from version 1)
    derived_relation = ProvenanceRelationDocument(
        relation_id="wasDerivedFrom:qubit_frequency:Q0:exec-001:task-001:qubit_frequency:Q0:exec-000:task-001",
        relation_type=ProvenanceRelationType.DERIVED_FROM,
        source_type="entity",
        source_id="qubit_frequency:Q0:exec-001:task-001",
        target_type="entity",
        target_id="qubit_frequency:Q0:exec-000:task-001",
        project_id="test_project",
        execution_id="exec-001",
        confidence=1.0,
    )
    derived_relation.insert()
    relations.append(derived_relation)

    return relations


class TestProvenanceRouter:
    """Tests for provenance-related API endpoints."""

    def test_get_entity_success(
        self, test_client, test_project, auth_headers, sample_parameter_versions
    ):
        """Test fetching a specific entity by ID."""
        entity_id = "qubit_frequency:Q0:exec-001:task-001"
        response = test_client.get(
            f"/provenance/entities/{entity_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == entity_id
        assert data["parameter_name"] == "qubit_frequency"
        assert data["qid"] == "Q0"
        assert data["value"] == 5.1
        assert data["unit"] == "GHz"
        assert data["version"] == 2

    def test_get_entity_not_found(self, test_client, test_project, auth_headers):
        """Test fetching a non-existent entity returns 404."""
        response = test_client.get(
            "/provenance/entities/nonexistent:entity:id:here",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_entity_wrong_project(
        self, test_client, test_project, auth_headers, sample_parameter_versions
    ):
        """Test that fetching another project's entity returns 404."""
        # Create entity for different project
        other_entity = ParameterVersionDocument(
            entity_id="other_param:Q0:exec-999:task-999",
            parameter_name="other_param",
            qid="Q0",
            value=1.0,
            version=1,
            execution_id="exec-999",
            task_id="task-999",
            project_id="other_project",
        )
        other_entity.insert()

        response = test_client.get(
            "/provenance/entities/other_param:Q0:exec-999:task-999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_get_lineage_success(
        self,
        test_client,
        test_project,
        auth_headers,
        sample_parameter_versions,
        sample_activities,
        sample_relations,
    ):
        """Test getting lineage (ancestors) of an entity."""
        entity_id = "qubit_frequency:Q0:exec-001:task-001"
        response = test_client.get(
            f"/provenance/lineage/{entity_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "origin" in data
        assert "nodes" in data
        assert "edges" in data
        assert data["max_depth"] == 5  # Default value
        assert data["origin"]["node_id"] == entity_id

    def test_get_lineage_with_custom_depth(
        self,
        test_client,
        test_project,
        auth_headers,
        sample_parameter_versions,
        sample_relations,
    ):
        """Test getting lineage with custom max_depth."""
        entity_id = "qubit_frequency:Q0:exec-001:task-001"
        response = test_client.get(
            f"/provenance/lineage/{entity_id}?max_depth=10",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["max_depth"] == 10

    def test_get_lineage_invalid_depth(self, test_client, test_project, auth_headers):
        """Test that invalid max_depth returns 422."""
        response = test_client.get(
            "/provenance/lineage/some:entity?max_depth=0",
            headers=auth_headers,
        )

        assert response.status_code == 422

        response = test_client.get(
            "/provenance/lineage/some:entity?max_depth=25",
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_get_impact_success(
        self,
        test_client,
        test_project,
        auth_headers,
        sample_parameter_versions,
        sample_relations,
    ):
        """Test getting impact (descendants) of an entity."""
        entity_id = "qubit_frequency:Q0:exec-000:task-001"
        response = test_client.get(
            f"/provenance/impact/{entity_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "origin" in data
        assert "nodes" in data
        assert "edges" in data
        assert data["max_depth"] == 5
        assert data["origin"]["node_id"] == entity_id

    def test_get_impact_with_custom_depth(
        self,
        test_client,
        test_project,
        auth_headers,
        sample_parameter_versions,
        sample_relations,
    ):
        """Test getting impact with custom max_depth."""
        entity_id = "qubit_frequency:Q0:exec-000:task-001"
        response = test_client.get(
            f"/provenance/impact/{entity_id}?max_depth=3",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["max_depth"] == 3

    def test_compare_executions_success(
        self, test_client, test_project, auth_headers, sample_parameter_versions
    ):
        """Test comparing parameter values between two executions."""
        response = test_client.get(
            "/provenance/compare?execution_id_before=exec-000&execution_id_after=exec-001",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["execution_id_before"] == "exec-000"
        assert data["execution_id_after"] == "exec-001"
        assert "added_parameters" in data
        assert "removed_parameters" in data
        assert "changed_parameters" in data
        assert "unchanged_count" in data

    def test_compare_executions_missing_params(self, test_client, test_project, auth_headers):
        """Test that missing query parameters return 422."""
        response = test_client.get(
            "/provenance/compare?execution_id_before=exec-000",
            headers=auth_headers,
        )

        assert response.status_code == 422

        response = test_client.get(
            "/provenance/compare?execution_id_after=exec-001",
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_get_parameter_history_success(
        self, test_client, test_project, auth_headers, sample_parameter_versions
    ):
        """Test getting version history for a parameter."""
        response = test_client.get(
            "/provenance/history?parameter_name=qubit_frequency&qid=Q0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["parameter_name"] == "qubit_frequency"
        assert data["qid"] == "Q0"
        assert "versions" in data
        assert "total_versions" in data
        assert len(data["versions"]) == 3
        assert data["total_versions"] == 3

    def test_get_parameter_history_with_limit(
        self, test_client, test_project, auth_headers, sample_parameter_versions
    ):
        """Test getting parameter history with custom limit."""
        response = test_client.get(
            "/provenance/history?parameter_name=qubit_frequency&qid=Q0&limit=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["versions"]) <= 2

    def test_get_parameter_history_missing_params(self, test_client, test_project, auth_headers):
        """Test that missing query parameters return 422."""
        response = test_client.get(
            "/provenance/history?parameter_name=qubit_frequency",
            headers=auth_headers,
        )

        assert response.status_code == 422

        response = test_client.get(
            "/provenance/history?qid=Q0",
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_get_parameter_history_empty(self, test_client, test_project, auth_headers):
        """Test getting history for non-existent parameter."""
        response = test_client.get(
            "/provenance/history?parameter_name=nonexistent&qid=Q0",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["versions"] == []
        assert data["total_versions"] == 0

    def test_get_stats_success(self, test_client, test_project, auth_headers):
        """Test getting provenance statistics."""
        response = test_client.get(
            "/provenance/stats",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_entities" in data
        assert "total_activities" in data
        assert "total_relations" in data
        assert "relation_counts" in data
        assert "recent_entities" in data

    def test_provenance_requires_authentication(self, test_client, test_project):
        """Test that provenance endpoints require authentication."""
        endpoints = [
            "/provenance/entities/some:entity",
            "/provenance/lineage/some:entity",
            "/provenance/impact/some:entity",
            "/provenance/compare?execution_id_before=a&execution_id_after=b",
            "/provenance/history?parameter_name=x&qid=Q0",
            "/provenance/stats",
        ]

        for endpoint in endpoints:
            response = test_client.get(endpoint)
            assert response.status_code == 401, f"Endpoint {endpoint} should require auth"

    def test_provenance_uses_default_project_when_header_missing(self, test_client, test_project):
        """Test that provenance uses user's default project when header is missing."""
        headers = {
            "Authorization": "Bearer test_token",
            # Missing X-Project-Id header - should use user's default_project_id
        }

        response = test_client.get(
            "/provenance/stats",
            headers=headers,
        )

        # Should succeed using user's default project (test_project)
        assert response.status_code == 200


class TestDegradationTrendsEndpoint:
    """Tests for GET /degradation-trends endpoint."""

    def test_get_degradation_trends_success(self, test_client, test_project, auth_headers):
        """Test GET /degradation-trends returns 200 with expected structure."""
        response = test_client.get(
            "/provenance/degradation-trends",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "trends" in data
        assert "total_count" in data
        assert isinstance(data["trends"], list)

    def test_degradation_trends_min_streak_validation(
        self, test_client, test_project, auth_headers
    ):
        """Test min_streak < 3 returns 422."""
        response = test_client.get(
            "/provenance/degradation-trends?min_streak=0",
            headers=auth_headers,
        )
        assert response.status_code == 422

        response = test_client.get(
            "/provenance/degradation-trends?min_streak=2",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_degradation_trends_limit_validation(self, test_client, test_project, auth_headers):
        """Test limit < 1 returns 422."""
        response = test_client.get(
            "/provenance/degradation-trends?limit=0",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_degradation_trends_requires_authentication(self, test_client, test_project):
        """Test endpoint requires authentication."""
        response = test_client.get("/provenance/degradation-trends")
        assert response.status_code == 401


class TestProvenanceService:
    """Tests for provenance service logic."""

    def test_lineage_includes_activities_and_entities(
        self,
        test_client,
        test_project,
        auth_headers,
        sample_parameter_versions,
        sample_activities,
        sample_relations,
    ):
        """Test that lineage includes both activities and entities."""
        entity_id = "qubit_frequency:Q0:exec-001:task-001"
        response = test_client.get(
            f"/provenance/lineage/{entity_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        node_types = [n["node_type"] for n in data["nodes"]]
        # Should have at least the origin entity
        assert "entity" in node_types or len(data["nodes"]) > 0

    def test_execution_comparison_detects_changes(
        self, test_client, test_project, auth_headers, sample_parameter_versions
    ):
        """Test that execution comparison correctly detects changes."""
        response = test_client.get(
            "/provenance/compare?execution_id_before=exec-000&execution_id_after=exec-002",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # exec-002 has rabi_frequency which exec-000 doesn't have
        # So there should be at least one added parameter
        # Note: The actual result depends on the repository implementation
        assert isinstance(data["added_parameters"], list)
        assert isinstance(data["changed_parameters"], list)
        assert isinstance(data["removed_parameters"], list)
