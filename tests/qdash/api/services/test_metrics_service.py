"""Tests for metrics_service helpers."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from starlette.exceptions import HTTPException

from qdash.api.services.metrics_service import MetricsService, _parse_date_range
from qdash.common.config.metrics import load_metrics_config


def test_coupling_strength_is_extracted_with_mhz_display_config():
    repository = MagicMock()
    repository.aggregate_latest_metrics.return_value = {
        "qubit_qubit_coupling_strength": {
            "0-1": {"value": 5.0, "task_id": "task-1", "execution_id": "exec-1"}
        }
    }
    service = MetricsService(repository, MagicMock())

    metrics = service.extract_entity_metrics("chip-1", "project-1", "coupling")

    assert (
        "qubit_qubit_coupling_strength"
        in repository.aggregate_latest_metrics.call_args.kwargs["metric_keys"]
    )
    result = metrics["qubit_qubit_coupling_strength"]["0-1"]
    assert result.value == 5.0
    assert result.task_id == "task-1"
    metadata = load_metrics_config().coupling_metrics["qubit_qubit_coupling_strength"]
    assert metadata.unit == "MHz"
    assert metadata.scale == 1
    assert result.value * metadata.scale == pytest.approx(5.0)
    assert metadata.evaluation.mode == "none"


def test_readout_amplitude_is_an_overview_qubit_metric_in_arbitrary_units():
    metadata = load_metrics_config().qubit_metrics["readout_amplitude"]

    assert metadata.title == "Readout Amplitude"
    # Matches the a.u. unit of the readout_amplitude task outputs; no display scaling.
    assert metadata.unit == "a.u."
    assert metadata.scale == 1
    # Amplitude has no better direction, so "best" selection must not rank it.
    assert metadata.evaluation.mode == "none"


def test_readout_amplitude_is_extracted_keeping_zero_and_omitting_missing_qubits():
    repository = MagicMock()
    repository.aggregate_latest_metrics.return_value = {
        "readout_amplitude": {
            "0": {"value": 0.12, "task_id": "task-0", "execution_id": "exec-1"},
            "1": {"value": 0.0, "task_id": "task-1", "execution_id": "exec-1"},
        }
    }
    service = MetricsService(repository, MagicMock())

    metrics = service.extract_entity_metrics("chip-1", "project-1", "qubit")

    assert (
        "readout_amplitude" in repository.aggregate_latest_metrics.call_args.kwargs["metric_keys"]
    )
    values = metrics["readout_amplitude"]
    assert values["0"].value == pytest.approx(0.12)
    assert values["0"].task_id == "task-0"
    assert values["1"].value == 0.0
    assert "2" not in values


def test_readout_amplitude_is_skipped_by_best_selection():
    repository = MagicMock()
    repository.aggregate_best_metrics.return_value = {}
    service = MetricsService(repository, MagicMock())

    metrics = service.extract_entity_metrics("chip-1", "project-1", "qubit", selection_mode="best")

    metric_modes = repository.aggregate_best_metrics.call_args.kwargs["metric_modes"]
    assert "readout_amplitude" not in metric_modes
    assert metrics["readout_amplitude"] == {}


def test_latest_fh_metrics_preserve_values_and_reported_stddev():
    repository = MagicMock()
    values = {
        "fh_frequency": 4.516,
        "charging_energy": 0.24,
        "josephson_energy_first_harmonic": 15.0,
        "josephson_energy_second_harmonic": -0.15,
    }
    repository.aggregate_latest_metrics.return_value = {
        name: {"0": {"value": value, "task_id": "task-1", "execution_id": "exec-1", "stddev": 0.0}}
        for name, value in values.items()
    }
    service = MetricsService(repository, MagicMock())

    latest = service.extract_entity_metrics("chip-1", "project-1", "qubit")

    assert values.keys() <= repository.aggregate_latest_metrics.call_args.kwargs["metric_keys"]
    for name, value in values.items():
        assert latest[name]["0"].value == value
        assert latest[name]["0"].stddev == 0.0


class TestParseDateRange:
    """Tests for _parse_date_range absolute date-range parsing."""

    def test_both_none_returns_none_pair(self):
        start, end = _parse_date_range(None, None)
        assert start is None
        assert end is None

    def test_empty_strings_become_none(self):
        start, end = _parse_date_range("", "")
        assert start is None
        assert end is None

    def test_whitespace_only_strings_become_none(self):
        start, end = _parse_date_range("   ", "\t\n")
        assert start is None
        assert end is None

    def test_empty_start_with_valid_end(self):
        start, end = _parse_date_range("", "2026-01-02T00:00:00+09:00")
        assert start is None
        assert isinstance(end, datetime)

    def test_valid_start_with_empty_end(self):
        start, end = _parse_date_range("2026-01-01T00:00:00+09:00", "")
        assert isinstance(start, datetime)
        assert end is None

    def test_valid_iso8601_pair(self):
        start, end = _parse_date_range(
            "2026-01-01T00:00:00+09:00",
            "2026-01-02T00:00:00+09:00",
        )
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        assert start < end

    def test_invalid_string_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_date_range("not-a-date", None)
        assert exc_info.value.status_code == 400

    def test_inverted_range_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_date_range(
                "2026-01-02T00:00:00+09:00",
                "2026-01-01T00:00:00+09:00",
            )
        assert exc_info.value.status_code == 400
        assert "start_at must be on or before end_at" in exc_info.value.detail
