"""Tests for SeedImportService."""

from unittest.mock import MagicMock, patch

import pytest
import yaml
from qdash.api.schemas.calibration import (
    SeedImportRequest,
    SeedImportSource,
)
from qdash.api.services.seed_import_service import SeedImportService


class TestSeedImportServicePathValidation:
    """Tests for path traversal prevention in SeedImportService."""

    @pytest.fixture
    def service(self):
        """Create SeedImportService instance."""
        return SeedImportService()

    def test_params_dir_valid_chip_id(self, service):
        """Test _params_dir accepts valid chip IDs."""
        # Alphanumeric
        result = service._params_dir("chip001")
        assert "chip001" in str(result)

        # With underscore
        result = service._params_dir("chip_001")
        assert "chip_001" in str(result)

        # With hyphen
        result = service._params_dir("chip-001")
        assert "chip-001" in str(result)

        # Mixed
        result = service._params_dir("CHIP_001-test")
        assert "CHIP_001-test" in str(result)

    def test_params_dir_rejects_path_traversal(self, service):
        """Test _params_dir rejects path traversal attempts."""
        # Parent directory traversal
        with pytest.raises(ValueError, match="Invalid chip_id"):
            service._params_dir("../../../etc/passwd")

        with pytest.raises(ValueError, match="Invalid chip_id"):
            service._params_dir("..%2F..%2F..%2Fetc%2Fpasswd")

    def test_params_dir_rejects_special_characters(self, service):
        """Test _params_dir rejects special characters."""
        invalid_ids = [
            "chip/001",  # Forward slash
            "chip\\001",  # Backslash
            "chip;001",  # Semicolon
            "chip:001",  # Colon
            "chip 001",  # Space
            "chip.001",  # Dot
            "chip@001",  # At sign
            "chip#001",  # Hash
            "chip$001",  # Dollar
            "chip%001",  # Percent
            "chip*001",  # Asterisk
            "chip?001",  # Question mark
            "chip|001",  # Pipe
            "chip<001",  # Less than
            "chip>001",  # Greater than
            'chip"001',  # Quote
            "chip'001",  # Single quote
            "chip`001",  # Backtick
            "chip\n001",  # Newline
            "chip\t001",  # Tab
        ]

        for chip_id in invalid_ids:
            with pytest.raises(ValueError, match="Invalid chip_id"):
                service._params_dir(chip_id)

    def test_params_dir_rejects_empty_string(self, service):
        """Test _params_dir rejects empty chip ID."""
        with pytest.raises(ValueError, match="Invalid chip_id"):
            service._params_dir("")

    def test_params_dir_returns_correct_path(self, service):
        """Test _params_dir returns correct path structure."""
        result = service._params_dir("chip001")
        assert result.name == "params"
        assert result.parent.name == "chip001"


class TestSeedImportServiceImportSeeds:
    """Tests for import_seeds method."""

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories."""
        with (
            patch(
                "qdash.api.services.seed_import_service.MongoActivityRepository"
            ) as activity_repo,
            patch(
                "qdash.api.services.seed_import_service.MongoParameterVersionRepository"
            ) as param_repo,
            patch(
                "qdash.api.services.seed_import_service.MongoProvenanceRelationRepository"
            ) as relation_repo,
        ):
            mock_activity = MagicMock()
            mock_activity.activity_id = "test-activity-id"
            activity_repo.return_value.create_activity.return_value = mock_activity

            yield {
                "activity": activity_repo,
                "param_version": param_repo,
                "relation": relation_repo,
            }

    @pytest.fixture
    def service(self, mock_repos):
        """Create SeedImportService with mocked dependencies."""
        return SeedImportService()

    def test_import_seeds_raises_for_unknown_source(self, service):
        """Test import_seeds raises error for unknown source."""
        request = MagicMock()
        request.source = "UNKNOWN"

        with pytest.raises(ValueError, match="Unknown source"):
            service.import_seeds(request, "project-001", "user001")


class TestSeedImportServiceImportFromManual:
    """Tests for _import_from_manual method."""

    @pytest.fixture
    def mock_deps(self):
        """Create mock dependencies."""
        with (
            patch(
                "qdash.api.services.seed_import_service.MongoActivityRepository"
            ) as activity_repo,
            patch(
                "qdash.api.services.seed_import_service.MongoParameterVersionRepository"
            ) as param_repo,
            patch(
                "qdash.api.services.seed_import_service.MongoProvenanceRelationRepository"
            ) as relation_repo,
            patch("qdash.api.services.seed_import_service.QubitDocument") as qubit_doc,
        ):
            mock_activity = MagicMock()
            mock_activity.activity_id = "test-activity-id"
            activity_repo.return_value.create_activity.return_value = mock_activity

            qubit_doc.find_one.return_value.run.return_value = None

            yield {
                "activity": activity_repo,
                "param_version": param_repo,
                "relation": relation_repo,
                "qubit_doc": qubit_doc,
            }

    @pytest.fixture
    def service(self, mock_deps):
        """Create SeedImportService with mocked dependencies."""
        return SeedImportService()

    def test_import_from_manual_requires_manual_data(self, service):
        """Test _import_from_manual raises error when manual_data is missing."""
        request = SeedImportRequest(
            chip_id="chip001",
            source=SeedImportSource.MANUAL,
            manual_data=None,
        )

        with pytest.raises(ValueError, match="manual_data is required"):
            service._import_from_manual(request, "project-001", "user001")

    def test_import_from_manual_skips_null_values(self, service, mock_deps):
        """Test _import_from_manual skips null values."""
        request = SeedImportRequest(
            chip_id="chip001",
            source=SeedImportSource.MANUAL,
            manual_data={
                "qubit_frequency": {
                    "Q0": 5.0,
                    "Q1": None,  # Should be skipped
                }
            },
        )

        result = service._import_from_manual(request, "project-001", "user001")

        assert result.imported_count == 1
        assert result.skipped_count == 1

    def test_import_from_manual_handles_dict_values(self, service, mock_deps):
        """Test _import_from_manual handles dict values with value/unit."""
        request = SeedImportRequest(
            chip_id="chip001",
            source=SeedImportSource.MANUAL,
            manual_data={
                "qubit_frequency": {
                    "Q0": {"value": 5.0, "unit": "GHz"},
                }
            },
        )

        result = service._import_from_manual(request, "project-001", "user001")

        assert result.imported_count == 1
        assert result.results[0].value == 5.0
        assert result.results[0].unit == "GHz"

    def test_import_from_manual_filters_by_qids(self, service, mock_deps):
        """Test _import_from_manual filters by specified qids."""
        request = SeedImportRequest(
            chip_id="chip001",
            source=SeedImportSource.MANUAL,
            manual_data={
                "qubit_frequency": {
                    "Q0": 5.0,
                    "Q1": 5.1,
                    "Q2": 5.2,
                }
            },
            qids=["Q0", "Q2"],  # Only import Q0 and Q2
        )

        result = service._import_from_manual(request, "project-001", "user001")

        assert result.imported_count == 2
        imported_qids = [r.qid for r in result.results if r.status == "imported"]
        assert "Q0" in imported_qids
        assert "Q2" in imported_qids
        assert "Q1" not in imported_qids


class TestSeedImportServiceImportFromQubex:
    """Tests for _import_from_qubex method."""

    @pytest.fixture
    def mock_deps(self):
        """Create mock dependencies."""
        with (
            patch(
                "qdash.api.services.seed_import_service.MongoActivityRepository"
            ) as activity_repo,
            patch(
                "qdash.api.services.seed_import_service.MongoParameterVersionRepository"
            ) as param_repo,
            patch(
                "qdash.api.services.seed_import_service.MongoProvenanceRelationRepository"
            ) as relation_repo,
            patch("qdash.api.services.seed_import_service.QubitDocument") as qubit_doc,
        ):
            mock_activity = MagicMock()
            mock_activity.activity_id = "test-activity-id"
            activity_repo.return_value.create_activity.return_value = mock_activity

            qubit_doc.find_one.return_value.run.return_value = None

            yield {
                "activity": activity_repo,
                "param_version": param_repo,
                "relation": relation_repo,
                "qubit_doc": qubit_doc,
            }

    @pytest.fixture
    def service(self, mock_deps):
        """Create SeedImportService with mocked dependencies."""
        return SeedImportService()

    def test_import_from_qubex_skips_missing_files(self, service, mock_deps, tmp_path):
        """Test _import_from_qubex skips missing parameter files."""
        # Set up a temporary params directory with no files
        service._config_base = str(tmp_path)
        params_dir = tmp_path / "chip001" / "params"
        params_dir.mkdir(parents=True)

        request = SeedImportRequest(
            chip_id="chip001",
            source=SeedImportSource.QUBEX_PARAMS,
            parameters=["qubit_frequency"],  # This file doesn't exist
        )

        result = service._import_from_qubex(request, "project-001", "user001")

        assert result.imported_count == 0
        assert result.skipped_count == 1

    def test_import_from_qubex_loads_yaml_correctly(self, service, mock_deps, tmp_path):
        """Test _import_from_qubex correctly loads and imports YAML files."""
        # Set up a temporary params directory with a YAML file
        service._config_base = str(tmp_path)
        params_dir = tmp_path / "chip001" / "params"
        params_dir.mkdir(parents=True)

        yaml_content = """
meta:
  unit: GHz
data:
  Q0: 5.0
  Q1: 5.1
"""
        (params_dir / "qubit_frequency.yaml").write_text(yaml_content)

        request = SeedImportRequest(
            chip_id="chip001",
            source=SeedImportSource.QUBEX_PARAMS,
            parameters=["qubit_frequency"],
        )

        result = service._import_from_qubex(request, "project-001", "user001")

        assert result.imported_count == 2
        assert result.chip_id == "chip001"

    def test_import_from_qubex_skips_null_values_in_yaml(self, service, mock_deps, tmp_path):
        """Test _import_from_qubex skips null values in YAML."""
        service._config_base = str(tmp_path)
        params_dir = tmp_path / "chip001" / "params"
        params_dir.mkdir(parents=True)

        yaml_content = """
meta:
  unit: GHz
data:
  Q0: 5.0
  Q1: null
"""
        (params_dir / "qubit_frequency.yaml").write_text(yaml_content)

        request = SeedImportRequest(
            chip_id="chip001",
            source=SeedImportSource.QUBEX_PARAMS,
            parameters=["qubit_frequency"],
        )

        result = service._import_from_qubex(request, "project-001", "user001")

        assert result.imported_count == 1
        assert result.skipped_count == 1


class TestSeedImportServiceLoadParamYaml:
    """Tests for _load_param_yaml method."""

    @pytest.fixture
    def service(self):
        """Create SeedImportService instance."""
        return SeedImportService()

    def test_load_param_yaml_parses_correctly(self, service, tmp_path):
        """Test _load_param_yaml correctly parses YAML content."""
        yaml_content = """
meta:
  unit: GHz
  description: Qubit frequency
data:
  Q0: 5.0
  Q1: 5.1
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)

        result = service._load_param_yaml(yaml_file)

        assert "meta" in result
        assert "data" in result
        assert result["meta"]["unit"] == "GHz"
        assert result["data"]["Q0"] == 5.0
        assert result["data"]["Q1"] == 5.1

    def test_load_param_yaml_handles_empty_file(self, service, tmp_path):
        """Test _load_param_yaml handles empty file."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        result = service._load_param_yaml(yaml_file)

        assert result is None

    def test_load_param_yaml_raises_for_invalid_yaml(self, service, tmp_path):
        """Test _load_param_yaml raises error for invalid YAML."""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("invalid: yaml: content: [")

        with pytest.raises(yaml.YAMLError):
            service._load_param_yaml(yaml_file)


class TestSeedImportServiceValueComparison:
    """Tests for _values_equal method."""

    @pytest.fixture
    def service(self):
        """Create SeedImportService instance."""
        return SeedImportService()

    def test_values_equal_for_identical_floats(self, service):
        """Test _values_equal returns True for identical floats."""
        assert service._values_equal(5.0, 5.0) is True

    def test_values_equal_for_close_floats(self, service):
        """Test _values_equal returns True for close floats within tolerance."""
        # Values within 1e-9 relative tolerance (default)
        assert service._values_equal(5.0, 5.0 + 1e-10) is True
        # Values outside 1e-9 relative tolerance
        assert service._values_equal(5.0, 5.04) is False

    def test_values_equal_for_different_floats(self, service):
        """Test _values_equal returns False for different floats."""
        # Values outside 1% relative tolerance
        assert service._values_equal(5.0, 5.1) is False

    def test_values_equal_for_zero_values(self, service):
        """Test _values_equal handles zero values correctly."""
        assert service._values_equal(0.0, 0.0) is True
        # With 1e-9 absolute tolerance for zero comparison
        assert service._values_equal(0.0, 1e-10) is True  # Within tolerance
        assert service._values_equal(0.0, 0.001) is False  # Outside tolerance
        assert service._values_equal(0.0, 1.0) is False

    def test_values_equal_for_non_numeric(self, service):
        """Test _values_equal uses equality for non-numeric values."""
        assert service._values_equal("value", "value") is True
        assert service._values_equal("value1", "value2") is False
        assert service._values_equal([1, 2], [1, 2]) is True
        assert service._values_equal([1, 2], [1, 3]) is False
