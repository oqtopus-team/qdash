"""Comprehensive tests for flow service validation."""

from __future__ import annotations

import ast
import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from qdash.api.services.flow_service.validation import (
    _has_flow_decorator,
    format_with_ruff,
    normalize_folder,
    validate_flow_code,
    validate_flow_name,
)


def _function_def(source: str) -> ast.FunctionDef:
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    return node


class TestValidateFlowName:
    """validate_flow_name rejects names that are not alphanumeric/underscore."""

    def test_valid_names(self):
        validate_flow_name("my_flow")
        validate_flow_name("flow123")
        validate_flow_name("a_b_c")
        validate_flow_name("123flow")
        validate_flow_name("__")

    def test_invalid_name_with_dot(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_flow_name("my.flow")
        assert exc_info.value.status_code == 400
        assert "alphanumeric" in exc_info.value.detail

    def test_invalid_name_with_hyphen(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_flow_name("my-flow")
        assert exc_info.value.status_code == 400

    def test_invalid_name_with_space(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_flow_name("my flow")
        assert exc_info.value.status_code == 400

    def test_invalid_name_empty(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_flow_name("")
        assert exc_info.value.status_code == 400

    def test_invalid_name_with_trailing_newline(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_flow_name("my_flow\n")
        assert exc_info.value.status_code == 400

    def test_invalid_name_with_unicode(self):
        with pytest.raises(HTTPException):
            validate_flow_name("föö")


class TestNormalizeFolder:
    """normalize_folder canonicalizes slash/whitespace and validates segments."""

    def test_root_and_empty(self):
        assert normalize_folder("") == ""
        assert normalize_folder("/") == ""
        assert normalize_folder("   ") == ""
        assert normalize_folder("///") == ""

    def test_whitespace_only(self):
        assert normalize_folder("   /   ") == ""

    def test_single_segment(self):
        assert normalize_folder("daily") == "daily"

    def test_leading_trailing_slashes_stripped(self):
        assert normalize_folder("/daily/t1/") == "daily/t1"
        assert normalize_folder("/daily/t1") == "daily/t1"
        assert normalize_folder("daily/t1/") == "daily/t1"

    def test_whitespace_trimmed(self):
        assert normalize_folder("  daily/t1  ") == "daily/t1"

    def test_multiple_valid_segments(self):
        assert normalize_folder("/daily/t1/monitoring/") == "daily/t1/monitoring"

    def test_invalid_segment_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            normalize_folder("/daily/my flow/")
        assert exc_info.value.status_code == 400
        assert "segments" in exc_info.value.detail

    def test_invalid_segment_with_internal_newline_rejected(self):
        with pytest.raises(HTTPException):
            normalize_folder("daily/my_flow\nstuff")


class TestValidateFlowCode:
    """validate_flow_code ensures the expected @flow function exists."""

    def test_valid_code_name_form(self):
        code = "\n@flow\ndef my_flow():\n    pass\n"
        validate_flow_code(code, "my_flow")

    def test_valid_code_call_form(self):
        code = '\n@flow(my_param="value")\ndef my_flow():\n    pass\n'
        validate_flow_code(code, "my_flow")

    def test_syntax_error_rejected(self):
        code = "def my_flow():"
        with pytest.raises(HTTPException) as exc_info:
            validate_flow_code(code, "my_flow")
        assert exc_info.value.status_code == 400
        assert "syntax error" in exc_info.value.detail.lower()

    def test_no_flow_decorator_rejected(self):
        code = "\ndef regular_function():\n    pass\n"
        with pytest.raises(HTTPException) as exc_info:
            validate_flow_code(code, "my_flow")
        assert "No @flow" in exc_info.value.detail

    def test_expected_function_not_found_rejected(self):
        code = "\n@flow\ndef other_function():\n    pass\n"
        with pytest.raises(HTTPException) as exc_info:
            validate_flow_code(code, "my_flow")
        assert "Flow function 'my_flow'" in exc_info.value.detail
        assert "other_function" in exc_info.value.detail

    def test_multiple_flow_functions_accepts_expected(self):
        code = "\n@flow\ndef my_flow():\n    pass\n\n@flow\ndef other_flow():\n    pass\n"
        validate_flow_code(code, "my_flow")

    def test_function_with_body_accepted(self):
        code = "\n@flow\ndef my_flow():\n    return 42\n"
        validate_flow_code(code, "my_flow")

    def test_class_method_without_flow_decorator_rejected(self):
        code = "\nclass Runner:\n    def run(self):\n        pass\n"
        with pytest.raises(HTTPException):
            validate_flow_code(code, "my_flow")


class TestHasFlowDecorator:
    """_has_flow_decorator identifies @flow and @flow(...) on FunctionDef nodes."""

    def test_name_form(self):
        node = _function_def("@flow\ndef my_func():\n    pass\n")
        assert _has_flow_decorator(node) is True

    def test_call_form(self):
        node = _function_def("@flow(retries=2)\ndef my_func():\n    pass\n")
        assert _has_flow_decorator(node) is True

    def test_no_decorator(self):
        node = _function_def("def my_func():\n    pass\n")
        assert _has_flow_decorator(node) is False

    def test_other_decorator(self):
        node = _function_def("@other\ndef my_func():\n    pass\n")
        assert _has_flow_decorator(node) is False


class TestFormatWithRuff:
    """format_with_ruff is best-effort; failures are logged, not raised."""

    @patch("subprocess.run")
    def test_success_logs_info(self, mock_run, caplog):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with caplog.at_level(logging.INFO):
            format_with_ruff(Path("/tmp/test_flow.py"))
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ruff"
        assert cmd[1] == "format"
        assert "Auto-formatted flow code with ruff" in caplog.text

    @patch("subprocess.run")
    def test_timeout_logs_warning(self, mock_run, caplog):
        mock_run.side_effect = subprocess.TimeoutExpired("ruff", 10)
        with caplog.at_level(logging.WARNING):
            format_with_ruff(Path("/tmp/test_flow.py"))
        assert "Ruff format timeout" in caplog.text

    @patch("subprocess.run")
    def test_not_found_logs_warning(self, mock_run, caplog):
        mock_run.side_effect = FileNotFoundError("ruff not found")
        with caplog.at_level(logging.WARNING):
            format_with_ruff(Path("/tmp/test_flow.py"))
        assert "Ruff not found" in caplog.text

    @patch("subprocess.run")
    def test_non_zero_exit_logs_warning(self, mock_run, caplog):
        mock_run.return_value = MagicMock(returncode=1, stderr="some error")
        with caplog.at_level(logging.WARNING):
            format_with_ruff(Path("/tmp/test_flow.py"))
        assert "non-zero exit code" in caplog.text


class TestFormatWithRuffGeneric:
    """format_with_ruff generic exception branch."""

    @patch("subprocess.run")
    def test_generic_exception_logs_warning(self, mock_run, caplog):
        mock_run.side_effect = ValueError("boom")
        with caplog.at_level(logging.WARNING):
            format_with_ruff(Path("/tmp/test_flow.py"))
        assert "Failed to auto-format with ruff" in caplog.text
