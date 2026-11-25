"""Task result parameters: stable Parameter values with their reported metadata."""

from __future__ import annotations

import datetime as dt
import sys
from typing import Any

import httpx
import pytest
from test_sdk_results import CHIP, FIGURE
from test_sdk_session import Server

from qdash.sdk import Parameter, Parameters
from qdash.sdk._parameters import PARAMETER_COLUMNS


def saved(**parameters: Any) -> dict[str, Any]:
    return {
        "task_id": "t-1",
        "task_name": "CheckT1",
        "qid": "0",
        "chip_id": CHIP,
        "status": "completed",
        "execution_id": "exec-9",
        "figure_path": [FIGURE],
        "json_figure_path": [],
        "raw_data_path": [],
        "input_parameters": parameters.pop("inputs", {}),
        "output_parameters": parameters.pop("outputs", {}),
    }


def read(body: dict[str, Any]):
    server = Server({("GET", "/tasks/t-1/result"): [httpx.Response(200, json=body)]})
    with server.session() as qdash:
        return qdash.task_result("t-1")


T1 = {
    "parameter_name": "t1",
    "value": 31.5,
    "unit": "us",
    "error": 1.2,
    "value_type": "float",
    "description": "Relaxation time",
    "calibrated_at": "2026-11-24T01:02:03Z",
    "execution_id": "exec-9",
    "task_id": "t-1",
    "source": {"task_name": "CheckT1", "execution_id": "exec-9"},
    "database_updated": False,
    "previous_database_value": None,
    "future_field": "kept",
}


def test_output_parameters_are_stable_values_with_their_metadata() -> None:
    task = read(saved(outputs={"t1": T1}))

    params = task.output_parameters
    assert isinstance(params, Parameters)
    t1 = params["t1"]
    assert isinstance(t1, Parameter)
    assert repr(t1) == "Parameter(value=31.5, unit='us', error=1.2)"
    assert "CalibratedAt" not in repr(params)
    assert (t1.value, t1.unit, t1.error) == (31.5, "us", 1.2)
    assert t1.calibrated_at == dt.datetime(2026, 11, 24, 1, 2, 3, tzinfo=dt.UTC)
    assert (t1.execution_id, t1.task_id) == ("exec-9", "t-1")
    assert (t1.description, t1.value_type) == ("Relaxation time", "float")
    # Every other reported field is kept as plain data, including ones the SDK does not know.
    assert t1.metadata["source"] == {"task_name": "CheckT1", "execution_id": "exec-9"}
    assert t1.metadata["database_updated"] is False
    assert "previous_database_value" in t1.metadata
    assert t1.metadata["previous_database_value"] is None
    assert t1.metadata["future_field"] == "kept"
    # Nothing the server left out is invented.
    assert "qid_role" not in t1.metadata
    assert "value" not in t1.metadata
    # The raw response stays reachable.
    assert task.detail.output_parameters["t1"] is t1.raw


def test_input_parameters_take_the_same_form() -> None:
    task = read(saved(inputs={"qubit_frequency": {"value": 5.1, "unit": "GHz"}}))

    frequency = task.input_parameters["qubit_frequency"]
    assert isinstance(frequency, Parameter)
    assert repr(frequency) == "Parameter(value=5.1, unit='GHz', error=None)"
    assert frequency.calibrated_at is None
    assert frequency.task_id is None
    assert dict(frequency.metadata) == {}


@pytest.mark.parametrize("legacy", [0.25, "pi/2", True, [1, 2, 3]])
def test_a_bare_value_from_an_older_result_becomes_the_value(legacy: Any) -> None:
    task = read(saved(outputs={"x": legacy}))

    x = task.output_parameters["x"]
    assert isinstance(x, Parameter)
    assert x.value == legacy
    assert (x.unit, x.error, dict(x.metadata)) == (None, None, {})


def test_a_parameter_listed_as_null_stays_none() -> None:
    task = read(saved(outputs={"skipped": None, "empty": {"value": None}}))

    params = task.output_parameters
    assert params["skipped"] is None
    empty = params["empty"]
    assert empty is not None and empty.value is None
    assert list(params) == ["skipped", "empty"]


def test_parameters_are_a_read_only_mapping_equal_to_its_items() -> None:
    params = Parameters.from_reported({"a": {"value": 1}, "b": None})

    assert len(params) == 2 and "a" in params
    assert params == {"a": Parameter(value=1), "b": None}
    assert Parameters() == {}
    with pytest.raises(TypeError):
        params["c"] = Parameter()  # type: ignore[index]
    assert repr(params) == "Parameters({'a': Parameter(value=1, unit=None, error=None), 'b': None})"


def test_to_records_has_fixed_columns() -> None:
    task = read(saved(outputs={"t1": T1, "skipped": None, "legacy": 3.0}))

    records = task.output_parameters.to_records()
    assert [list(row) for row in records] == [list(PARAMETER_COLUMNS)] * 3
    assert records[0]["value"] == 31.5
    assert records[0]["calibrated_at"] == dt.datetime(2026, 11, 24, 1, 2, 3, tzinfo=dt.UTC)
    assert records[1] == {
        column: ("skipped" if column == "name" else None) for column in PARAMETER_COLUMNS
    }
    assert (records[2]["value"], records[2]["unit"]) == (3.0, None)


def test_to_dataframe_has_stable_columns_even_when_empty() -> None:
    pandas = pytest.importorskip("pandas")
    frame = Parameters.from_reported({"t1": T1}).to_dataframe()

    assert isinstance(frame, pandas.DataFrame)
    assert list(frame.columns) == list(PARAMETER_COLUMNS)
    assert frame.loc[0, "unit"] == "us"
    assert list(Parameters().to_dataframe().columns) == list(PARAMETER_COLUMNS)


def test_to_dataframe_without_pandas_says_what_to_use(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pandas", None)
    with pytest.raises(ImportError, match="to_records"):
        Parameters().to_dataframe()


def test_a_unit_or_error_of_an_unexpected_type_is_kept_in_metadata() -> None:
    params = Parameters.from_reported(
        {
            "odd": {"value": 1, "unit": 3, "error": "n/a"},
            "flag": {"value": 1, "error": True},
            "plain": {"value": 1, "unit": "us", "error": 2},
        }
    )

    odd, flag, plain = params["odd"], params["flag"], params["plain"]
    assert odd is not None and flag is not None and plain is not None
    assert (odd.unit, odd.error) == (None, None)
    assert dict(odd.metadata) == {"unit": 3, "error": "n/a"}
    assert (flag.error, dict(flag.metadata)) == (None, {"error": True})
    assert (plain.unit, plain.error, dict(plain.metadata)) == ("us", 2, {})


def test_calibrated_at_from_a_mapping_is_parsed_when_it_is_iso_8601() -> None:
    params = Parameters.from_reported(
        {
            "a": {"value": 1, "calibrated_at": "2026-11-24T01:02:03Z"},
            "b": {"value": 1, "calibrated_at": "yesterday"},
        }
    )

    a, b = params["a"], params["b"]
    assert a is not None and b is not None
    assert a.calibrated_at == dt.datetime(2026, 11, 24, 1, 2, 3, tzinfo=dt.UTC)
    assert b.calibrated_at is None
    assert b.metadata["calibrated_at"] == "yesterday"


def test_a_parameter_cannot_be_reassigned_but_nested_values_are_not_copied() -> None:
    source = {"task_name": "CheckT1"}
    parameter = Parameter.from_reported({"value": [1, 2], "source": source})

    with pytest.raises(AttributeError):
        parameter.value = 3
    with pytest.raises(TypeError):
        parameter.metadata["source"] = {}  # type: ignore[index]
    # The guarantee is shallow: nested values are the reported objects.
    assert parameter.metadata["source"] is source
