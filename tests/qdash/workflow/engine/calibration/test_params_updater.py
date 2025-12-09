"""Tests for params_updater module."""

import io
import tempfile
from pathlib import Path

import pytest
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
