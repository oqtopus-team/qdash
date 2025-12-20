"""Tests for params_updater module."""

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from qdash.workflow.engine.params_updater import _QubexParamsUpdater
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


class TestParamsUpdaterNoneHandling:
    """Test that None values are properly represented as 'null' in YAML output."""

    def test_none_values_output_as_null(self):
        """Verify that None values are written as explicit 'null' in YAML."""
        from qdash.workflow.worker.flows.push_props.formatter import represent_none

        # Setup YAML the same way as _QubexParamsUpdater
        yaml_obj = YAML(typ="rt")
        yaml_obj.preserve_quotes = True
        yaml_obj.width = None
        yaml_obj.indent(mapping=2, sequence=4, offset=2)
        yaml_obj.representer.add_representer(type(None), represent_none)

        # Create test data with None values
        data = CommentedMap(
            {
                "data": CommentedMap(
                    {
                        "Q00": None,
                        "Q01": 5.5,
                        "Q02": None,
                    }
                )
            }
        )

        # Dump to string
        stream = io.StringIO()
        yaml_obj.dump(data, stream)
        result = stream.getvalue()

        # Verify None values are written as 'null'
        assert "Q00: null" in result, f"Q00 should be 'null', got: {result}"
        assert "Q02: null" in result, f"Q02 should be 'null', got: {result}"

    def test_yaml_none_outputs_null_text(self):
        """Verify that YAML output contains the text 'null' for None values.

        This test ensures consistency across ruamel.yaml versions.
        The key requirement is that None values are explicitly represented as 'null'
        in the YAML output, not as empty values.
        """
        from qdash.workflow.worker.flows.push_props.formatter import represent_none

        # Setup YAML with custom representer (as in params_updater)
        yaml_obj = YAML(typ="rt")
        yaml_obj.preserve_quotes = True
        yaml_obj.width = None
        yaml_obj.representer.add_representer(type(None), represent_none)

        data = CommentedMap({"data": CommentedMap({"Q00": None})})

        stream = io.StringIO()
        yaml_obj.dump(data, stream)
        result = stream.getvalue()

        # With our fix, None should be explicit 'null'
        assert "Q00: null" in result, f"Q00 should be 'null', got: {result}"

    def test_yaml_file_roundtrip_with_none(self):
        """Test that None values survive a write/read roundtrip."""
        from qdash.workflow.worker.flows.push_props.formatter import represent_none

        yaml_obj = YAML(typ="rt")
        yaml_obj.preserve_quotes = True
        yaml_obj.representer.add_representer(type(None), represent_none)

        data = CommentedMap({"data": CommentedMap({"Q00": None, "Q01": 5.5})})

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_obj.dump(data, f)
            temp_path = f.name

        try:
            # Read back and verify
            with open(temp_path) as f:
                loaded = yaml_obj.load(f)

            assert loaded["data"]["Q00"] is None, "Q00 should be None after roundtrip"
            assert loaded["data"]["Q01"] == 5.5, "Q01 should preserve value"

            # Check file content has explicit 'null'
            with open(temp_path) as f:
                content = f.read()
            assert "Q00: null" in content, "File should contain explicit 'null'"
        finally:
            Path(temp_path).unlink()


class TestUpdateYaml:
    """Test _update_yaml method with file locking and atomic write."""

    @pytest.fixture
    def updater(self):
        """Create a _QubexParamsUpdater instance with mocked backend."""
        backend = MagicMock()
        backend.config = {}
        return _QubexParamsUpdater(backend, chip_id=None)

    @pytest.fixture
    def yaml_file(self, tmp_path):
        """Create a temporary YAML file with initial data."""
        yaml_path = tmp_path / "test_params.yaml"
        yaml_path.write_text(
            """meta:
  description: Test parameter file
  unit: μs

data:
  Q00: 10.5
  Q01: 20.3
  Q02: null
"""
        )
        return yaml_path

    def test_update_existing_value(self, updater, yaml_file):
        """Test updating an existing qubit value."""
        updater._update_yaml(yaml_file, "Q00", 15.0)

        content = yaml_file.read_text()
        assert "Q00: 15.0" in content
        assert "meta:" in content  # meta section preserved
        assert "description: Test parameter file" in content

    def test_add_new_qubit_value(self, updater, yaml_file):
        """Test adding a new qubit value in correct order."""
        updater._update_yaml(yaml_file, "Q03", 30.5)

        content = yaml_file.read_text()
        assert "Q03: 30.5" in content
        assert "meta:" in content

    def test_meta_section_preserved(self, updater, yaml_file):
        """Test that meta section is preserved after update."""
        updater._update_yaml(yaml_file, "Q01", 25.0)

        content = yaml_file.read_text()
        assert "meta:" in content
        assert "description: Test parameter file" in content
        assert "unit: μs" in content

    def test_lock_file_created(self, updater, yaml_file):
        """Test that lock file is created during update."""
        updater._update_yaml(yaml_file, "Q00", 99.0)

        lock_path = yaml_file.with_suffix(".yaml.lock")
        assert lock_path.exists()

    def test_atomic_write_no_partial_content(self, updater, yaml_file):
        """Test that atomic write prevents partial content."""
        # Read original content
        yaml_file.read_text()

        # Update should be atomic
        updater._update_yaml(yaml_file, "Q00", 100.0)

        # File should be valid YAML
        yaml = YAML(typ="rt")
        with yaml_file.open("r") as f:
            data = yaml.load(f)

        assert data is not None
        assert "data" in data
        assert data["data"]["Q00"] == 100.0

    def test_no_change_when_value_equal(self, updater, yaml_file):
        """Test that file is not modified when value is unchanged."""
        original_mtime = yaml_file.stat().st_mtime

        # Update with same value
        updater._update_yaml(yaml_file, "Q00", 10.5)

        # File should not be modified
        new_mtime = yaml_file.stat().st_mtime
        assert original_mtime == new_mtime

    def test_nonexistent_file_is_skipped(self, updater, tmp_path):
        """Test that nonexistent file is gracefully skipped."""
        nonexistent = tmp_path / "nonexistent.yaml"

        # Should not raise
        updater._update_yaml(nonexistent, "Q00", 10.0)

    def test_insert_ordered_between_existing(self, updater, yaml_file):
        """Test that new qubit is inserted in correct order."""
        # Add Q05 first
        updater._update_yaml(yaml_file, "Q05", 50.0)

        # Then add Q03 - should be inserted between Q02 and Q05
        updater._update_yaml(yaml_file, "Q03", 30.0)

        content = yaml_file.read_text()
        q02_pos = content.find("Q02:")
        q03_pos = content.find("Q03:")
        q05_pos = content.find("Q05:")

        assert q02_pos < q03_pos < q05_pos, "Q03 should be between Q02 and Q05"
