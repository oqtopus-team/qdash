"""Tests for provenance repository."""

from datetime import datetime
from unittest.mock import ANY, MagicMock, patch

import pytest
from qdash.dbmodel.provenance import (
    ActivityDocument,
    ParameterVersionDocument,
    ProvenanceRelationDocument,
    ProvenanceRelationType,
)
from qdash.repository.provenance import (
    MongoActivityRepository,
    MongoParameterVersionRepository,
    MongoProvenanceRelationRepository,
)


class TestMongoParameterVersionRepository:
    """Test MongoParameterVersionRepository."""

    @pytest.fixture
    def repo(self):
        """Create repository instance."""
        return MongoParameterVersionRepository()

    def test_get_current_delegates_to_document(self, repo):
        """Test get_current delegates to ParameterVersionDocument."""
        mock_result = MagicMock()
        with patch.object(
            ParameterVersionDocument, "get_current_version", return_value=mock_result
        ) as mock_get:
            result = repo.get_current(
                project_id="project-001",
                parameter_name="qubit_frequency",
                qid="Q0",
            )

            mock_get.assert_called_once_with(
                project_id="project-001",
                parameter_name="qubit_frequency",
                qid="Q0",
            )
            assert result == mock_result

    def test_create_version_calls_invalidate_current(self, repo):
        """Test create_version calls invalidate_current before creating new version."""
        # Mock the entire ParameterVersionDocument class
        with patch("qdash.repository.provenance.ParameterVersionDocument") as MockDocument:
            MockDocument.get_next_version.return_value = 2
            MockDocument.generate_entity_id.return_value = "qubit_frequency:Q0:exec-001:task-001"

            mock_instance = MagicMock()
            mock_instance.entity_id = "qubit_frequency:Q0:exec-001:task-001"
            mock_instance.version = 2
            MockDocument.return_value = mock_instance

            entity = repo.create_version(
                parameter_name="qubit_frequency",
                qid="Q0",
                value=5.0,
                execution_id="exec-001",
                task_id="task-001",
                project_id="project-001",
                task_name="CheckQubit",
                chip_id="chip-001",
                unit="GHz",
                error=0.01,
                value_type="float",
            )

            MockDocument.invalidate_current.assert_called_once_with(
                project_id="project-001",
                parameter_name="qubit_frequency",
                qid="Q0",
                invalidated_at=ANY,
            )
            mock_instance.insert.assert_called_once()
            assert entity.entity_id == "qubit_frequency:Q0:exec-001:task-001"


class TestMongoProvenanceRelationRepository:
    """Test MongoProvenanceRelationRepository."""

    @pytest.fixture
    def repo(self):
        """Create repository instance."""
        return MongoProvenanceRelationRepository()

    def test_create_relation_delegates_to_document(self, repo):
        """Test create_relation delegates to ProvenanceRelationDocument."""
        mock_result = MagicMock()
        with patch.object(
            ProvenanceRelationDocument, "create_relation", return_value=mock_result
        ) as mock_create:
            result = repo.create_relation(
                relation_type=ProvenanceRelationType.GENERATED_BY,
                source_type="entity",
                source_id="entity-001",
                target_type="activity",
                target_id="activity-001",
                project_id="project-001",
                execution_id="exec-001",
                confidence=1.0,
                inference_method=None,
            )

            mock_create.assert_called_once_with(
                relation_type=ProvenanceRelationType.GENERATED_BY,
                source_type="entity",
                source_id="entity-001",
                target_type="activity",
                target_id="activity-001",
                project_id="project-001",
                execution_id="exec-001",
                confidence=1.0,
                inference_method=None,
            )
            assert result == mock_result


class TestMongoActivityRepository:
    """Test MongoActivityRepository."""

    @pytest.fixture
    def repo(self):
        """Create repository instance."""
        return MongoActivityRepository()

    def test_create_activity_generates_activity_id(self, repo):
        """Test create_activity generates correct activity ID."""
        with patch("qdash.repository.provenance.ActivityDocument") as MockDocument:
            MockDocument.find_one.return_value.run.return_value = None
            MockDocument.generate_activity_id.return_value = "exec-001:task-001"

            mock_instance = MagicMock()
            mock_instance.activity_id = "exec-001:task-001"
            MockDocument.return_value = mock_instance

            activity = repo.create_activity(
                execution_id="exec-001",
                task_id="task-001",
                task_name="CheckQubit",
                project_id="project-001",
                task_type="qubit",
                qid="Q0",
                chip_id="chip-001",
                started_at=datetime(2025, 1, 1, 10, 0, 0),
                ended_at=datetime(2025, 1, 1, 10, 5, 0),
                status="completed",
            )

            assert activity.activity_id == "exec-001:task-001"
            mock_instance.insert.assert_called_once()

    def test_create_activity_returns_existing(self, repo):
        """Test create_activity returns existing activity if found."""
        mock_existing = MagicMock()
        mock_existing.activity_id = "exec-001:task-001"

        with patch.object(ActivityDocument, "find_one") as mock_find:
            mock_find.return_value.run.return_value = mock_existing

            activity = repo.create_activity(
                execution_id="exec-001",
                task_id="task-001",
                task_name="CheckQubit",
                project_id="project-001",
                task_type="qubit",
                qid="Q0",
                chip_id="chip-001",
                started_at=datetime(2025, 1, 1, 10, 0, 0),
                ended_at=datetime(2025, 1, 1, 10, 5, 0),
                status="completed",
            )

            assert activity == mock_existing


class TestProvenanceRelationDocumentMethods:
    """Test ProvenanceRelationDocument class methods."""

    def test_generate_relation_id(self):
        """Test generate_relation_id creates correct format."""
        relation_id = ProvenanceRelationDocument.generate_relation_id(
            relation_type=ProvenanceRelationType.GENERATED_BY,
            source_id="entity-001",
            target_id="activity-001",
        )

        assert relation_id == "wasGeneratedBy:entity-001:activity-001"

    def test_generate_relation_id_used(self):
        """Test generate_relation_id for USED relation."""
        relation_id = ProvenanceRelationDocument.generate_relation_id(
            relation_type=ProvenanceRelationType.USED,
            source_id="activity-001",
            target_id="entity-001",
        )

        assert relation_id == "used:activity-001:entity-001"

    def test_generate_relation_id_derived_from(self):
        """Test generate_relation_id for DERIVED_FROM relation."""
        relation_id = ProvenanceRelationDocument.generate_relation_id(
            relation_type=ProvenanceRelationType.DERIVED_FROM,
            source_id="entity-002",
            target_id="entity-001",
        )

        assert relation_id == "wasDerivedFrom:entity-002:entity-001"


class TestParameterVersionDocumentMethods:
    """Test ParameterVersionDocument class methods."""

    def test_generate_entity_id(self):
        """Test generate_entity_id creates correct format."""
        entity_id = ParameterVersionDocument.generate_entity_id(
            parameter_name="qubit_frequency",
            qid="Q0",
            execution_id="exec-001",
            task_id="task-001",
        )

        assert entity_id == "qubit_frequency:Q0:exec-001:task-001"

    def test_generate_entity_id_with_coupling(self):
        """Test generate_entity_id with coupling qid."""
        entity_id = ParameterVersionDocument.generate_entity_id(
            parameter_name="coupling_strength",
            qid="Q0-Q1",
            execution_id="exec-001",
            task_id="task-002",
        )

        assert entity_id == "coupling_strength:Q0-Q1:exec-001:task-002"


class TestActivityDocumentMethods:
    """Test ActivityDocument class methods."""

    def test_generate_activity_id(self):
        """Test generate_activity_id creates correct format."""
        activity_id = ActivityDocument.generate_activity_id(
            execution_id="exec-001",
            task_id="task-001",
        )

        assert activity_id == "exec-001:task-001"


class TestProvenanceRelationType:
    """Test ProvenanceRelationType enum."""

    def test_relation_type_values(self):
        """Test relation type enum values."""
        assert ProvenanceRelationType.GENERATED_BY.value == "wasGeneratedBy"
        assert ProvenanceRelationType.USED.value == "used"
        assert ProvenanceRelationType.DERIVED_FROM.value == "wasDerivedFrom"
        assert ProvenanceRelationType.ATTRIBUTED_TO.value == "wasAttributedTo"
        assert ProvenanceRelationType.INVALIDATED_BY.value == "wasInvalidatedBy"
