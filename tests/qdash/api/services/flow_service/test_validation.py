"""Tests for flow name, folder and source validation."""

import pytest
from fastapi import HTTPException

from qdash.api.schemas.flow import SaveFlowRequest
from qdash.api.services.flow_service.validation import (
    normalize_folder,
    validate_flow_code,
    validate_flow_name,
)

FLOW_CODE = "from prefect import flow\n\n\n@flow\ndef my_flow():\n    pass\n"


@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("", ""),
        ("   ", ""),
        ("daily", "daily"),
        ("/daily/t1/", "daily/t1"),
        (" daily/t1 ", "daily/t1"),
    ],
)
def test_normalize_folder_canonicalizes_valid_paths(folder: str, expected: str) -> None:
    """Surrounding slashes and whitespace are dropped from valid folders."""
    assert normalize_folder(folder) == expected


@pytest.mark.parametrize("folder", ["daily//t1", "../t1", "daily t1", "daily/t1.py"])
def test_normalize_folder_rejects_bad_segments(folder: str) -> None:
    """A folder segment must look like a flow name."""
    with pytest.raises(HTTPException) as exc_info:
        normalize_folder(folder)
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize("name", ["my flow", "my-flow", "my.flow", "", "../flow"])
def test_validate_flow_name_rejects_unsafe_names(name: str) -> None:
    """Names are restricted to alphanumeric characters and underscores."""
    with pytest.raises(HTTPException) as exc_info:
        validate_flow_name(name)
    assert exc_info.value.status_code == 400


def test_validate_flow_name_accepts_alphanumeric_and_underscore_names() -> None:
    """The supported character set is accepted without error."""
    validate_flow_name("my_flow_2")


def test_validate_flow_code_accepts_the_expected_flow_function() -> None:
    """A @flow decorated function with the expected name is valid."""
    validate_flow_code(FLOW_CODE, "my_flow")


def test_validate_flow_code_accepts_a_decorator_call() -> None:
    """A @flow(...) decorator call counts as a flow function."""
    validate_flow_code("@flow(name='x')\ndef my_flow():\n    pass\n", "my_flow")


def test_validate_flow_code_rejects_a_syntax_error() -> None:
    """Unparseable code is rejected with the syntax error message."""
    with pytest.raises(HTTPException) as exc_info:
        validate_flow_code("def my_flow(:\n", "my_flow")
    assert exc_info.value.status_code == 400
    assert "Python syntax error" in str(exc_info.value.detail)


def test_validate_flow_code_rejects_code_without_a_flow_function() -> None:
    """Code that defines no flow function is rejected."""
    with pytest.raises(HTTPException) as exc_info:
        validate_flow_code("def helper():\n    pass\n", "my_flow")
    assert "No @flow decorated function" in str(exc_info.value.detail)


def test_validate_flow_code_rejects_a_name_mismatch() -> None:
    """The expected function name must be among the flow functions."""
    with pytest.raises(HTTPException) as exc_info:
        validate_flow_code(FLOW_CODE, "other_flow")
    assert "Flow function 'other_flow' not found" in str(exc_info.value.detail)


def test_save_request_distinguishes_an_omitted_folder_from_the_root() -> None:
    """An omitted folder keeps the stored folder; an empty string means the root."""
    assert SaveFlowRequest(name="f", code="", chip_id="c").folder is None
    assert SaveFlowRequest(name="f", code="", chip_id="c", folder="").folder == ""
