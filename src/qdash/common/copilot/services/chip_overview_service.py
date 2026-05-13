"""Chip-level summary and timeseries helpers for Copilot data loading."""

from __future__ import annotations

import math
import statistics as stats_mod
from dataclasses import dataclass
from typing import Any, Protocol


class ChipOverviewDataAccessProtocol(Protocol):
    """Subset of data-access methods used for chip overview loaders."""

    def load_chip_parameter_timeseries_docs(
        self,
        parameter_name: str,
        chip_id: str,
        last_n: int,
        qids: list[str] | None,
    ) -> list[Any]: ...

    def load_qubits_for_chip(self, chip_id: str) -> list[Any]: ...


@dataclass(frozen=True)
class ParameterTimeseriesEntry:
    """Normalized per-document value used for chip-level parameter timeseries."""

    value: Any
    start_at: str | None


class ChipOverviewLoader:
    """Load chip-wide summaries and per-parameter timeseries for Copilot tools."""

    def __init__(
        self,
        *,
        data_access: ChipOverviewDataAccessProtocol,
        compact_number: Any,
    ) -> None:
        self._data_access = data_access
        self._compact_number = compact_number

    def load_chip_parameter_timeseries(
        self,
        *,
        parameter_name: str,
        chip_id: str,
        last_n: int = 10,
        qids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Load per-qubit timeseries and summary for a parameter."""
        docs = self._data_access.load_chip_parameter_timeseries_docs(
            parameter_name,
            chip_id,
            last_n,
            qids,
        )
        per_qubit, unit = self._group_chip_parameter_timeseries(docs, parameter_name)
        if not per_qubit:
            return {"error": f"No data for '{parameter_name}' on chip '{chip_id}'"}

        qubits, timeseries, latest_values = self._summarize_chip_parameter_timeseries(
            per_qubit,
            last_n,
        )
        chip_stats = self._build_chip_parameter_statistics(latest_values)
        return {
            "chip_id": chip_id,
            "parameter_name": parameter_name,
            "unit": unit,
            "num_qubits": len(qubits),
            "statistics": chip_stats,
            "qubits": qubits,
            "timeseries": timeseries,
        }

    def _group_chip_parameter_timeseries(
        self,
        docs: list[Any],
        parameter_name: str,
    ) -> tuple[dict[str, list[ParameterTimeseriesEntry]], str]:
        """Group parameter timeseries documents by qid and normalize their values."""
        from collections import defaultdict

        per_qubit: dict[str, list[ParameterTimeseriesEntry]] = defaultdict(list)
        unit = ""
        for doc in docs:
            param_data = (doc.output_parameters or {}).get(parameter_name)
            if param_data is None:
                continue
            if isinstance(param_data, dict):
                value = param_data.get("value")
                if not unit:
                    unit = param_data.get("unit", "")
            else:
                value = param_data
            if value is None:
                continue
            per_qubit[doc.qid].append(
                ParameterTimeseriesEntry(
                    value=value,
                    start_at=doc.start_at.isoformat() if doc.start_at else None,
                )
            )
        return dict(per_qubit), unit

    def _summarize_chip_parameter_timeseries(
        self,
        per_qubit: dict[str, list[ParameterTimeseriesEntry]],
        last_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float]]:
        """Build per-qubit summaries, flat timeseries rows, and latest numeric values."""
        qubits: list[dict[str, Any]] = []
        timeseries: list[dict[str, Any]] = []
        latest_values: list[float] = []

        for qid, entries in sorted(
            per_qubit.items(),
            key=lambda item: int(item[0]) if item[0].isdigit() else item[0],
        ):
            recent_entries = entries[:last_n]
            qubit_summary, qid_timeseries, latest_value = (
                self._summarize_qubit_parameter_timeseries(
                    qid=qid,
                    entries=recent_entries,
                )
            )
            qubits.append(qubit_summary)
            timeseries.extend(qid_timeseries)
            if latest_value is not None:
                latest_values.append(latest_value)

        timeseries.sort(key=lambda row: row["t"])
        return qubits, timeseries, latest_values

    def _summarize_qubit_parameter_timeseries(
        self,
        *,
        qid: str,
        entries: list[ParameterTimeseriesEntry],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], float | None]:
        """Build summary rows for one qubit's parameter timeseries."""
        chronological_entries = list(reversed(entries))
        values = [entry.value for entry in entries]
        latest = values[0]
        latest_value = (
            float(latest) if isinstance(latest, (int, float)) and math.isfinite(latest) else None
        )

        qubit_summary: dict[str, Any] = {
            "qid": qid,
            "latest": self._compact_number(latest),
            "count": len(values),
            "min": None,
            "max": None,
            "mean": None,
            "trend": None,
        }
        numeric_values = [
            value for value in values if isinstance(value, (int, float)) and math.isfinite(value)
        ]
        if len(numeric_values) >= 2:
            qubit_summary["min"] = self._compact_number(min(numeric_values))
            qubit_summary["max"] = self._compact_number(max(numeric_values))
            qubit_summary["mean"] = self._compact_number(stats_mod.mean(numeric_values))
            qubit_summary["trend"] = self._classify_qubit_parameter_trend(numeric_values)

        timeseries_rows = [
            {"qid": qid, "t": entry.start_at or "", "v": entry.value}
            for entry in chronological_entries
        ]
        return qubit_summary, timeseries_rows, latest_value

    @staticmethod
    def _classify_qubit_parameter_trend(values: list[float]) -> str:
        """Classify trend direction from newest-first numeric values."""
        if values[0] > values[-1] * 1.01:
            return "up"
        if values[0] < values[-1] * 0.99:
            return "down"
        return "stable"

    def _build_chip_parameter_statistics(self, latest_values: list[float]) -> dict[str, Any]:
        """Build chip-wide statistics from the latest numeric value per qubit."""
        chip_stats: dict[str, Any] = {
            "count": len(latest_values),
            "mean": self._compact_number(stats_mod.mean(latest_values)) if latest_values else 0,
            "median": self._compact_number(stats_mod.median(latest_values)) if latest_values else 0,
            "min": self._compact_number(min(latest_values)) if latest_values else 0,
            "max": self._compact_number(max(latest_values)) if latest_values else 0,
        }
        if len(latest_values) >= 2:
            chip_stats["stdev"] = self._compact_number(stats_mod.stdev(latest_values))
        return chip_stats

    def load_chip_summary(
        self,
        *,
        chip_id: str,
        param_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Load summary of all qubits on a chip with computed statistics."""
        docs = self._data_access.load_qubits_for_chip(chip_id)
        if not docs:
            return {"error": f"No qubits found for chip_id={chip_id}"}

        raw_qubits, numeric_values = self._normalize_chip_summary_docs(docs, param_names)
        statistics = self._build_chip_summary_statistics(numeric_values)
        qubits = self._build_chip_summary_rows(raw_qubits)
        return {
            "chip_id": chip_id,
            "num_qubits": len(qubits),
            "statistics": statistics,
            "qubits": qubits,
        }

    def _normalize_chip_summary_docs(
        self,
        docs: list[Any],
        param_names: list[str] | None,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, list[float]]]:
        """Normalize qubit documents into raw value rows and numeric aggregates."""
        raw_qubits: dict[str, dict[str, Any]] = {}
        numeric_values: dict[str, list[float]] = {}

        for doc in docs:
            data = dict(doc.data)
            if param_names:
                data = {key: value for key, value in data.items() if key in param_names}

            compact: dict[str, Any] = {}
            for key, value in data.items():
                raw_value = (
                    value.get("value") if isinstance(value, dict) and "value" in value else value
                )
                compact[key] = raw_value
                if isinstance(raw_value, (int, float)) and math.isfinite(raw_value):
                    numeric_values.setdefault(key, []).append(float(raw_value))
            raw_qubits[doc.qid] = compact

        return raw_qubits, numeric_values

    def _build_chip_summary_statistics(
        self,
        numeric_values: dict[str, list[float]],
    ) -> dict[str, dict[str, float]]:
        """Build per-parameter descriptive statistics for a chip summary."""
        statistics: dict[str, dict[str, float]] = {}
        for key, values in numeric_values.items():
            if len(values) >= 2:
                statistics[key] = {
                    "mean": self._compact_number(stats_mod.mean(values)),
                    "median": self._compact_number(stats_mod.median(values)),
                    "stdev": self._compact_number(stats_mod.stdev(values)),
                    "min": self._compact_number(min(values)),
                    "max": self._compact_number(max(values)),
                    "count": len(values),
                }
            elif len(values) == 1:
                statistics[key] = {
                    "mean": self._compact_number(values[0]),
                    "median": self._compact_number(values[0]),
                    "stdev": 0.0,
                    "min": self._compact_number(values[0]),
                    "max": self._compact_number(values[0]),
                    "count": 1,
                }
        return statistics

    @staticmethod
    def _build_chip_summary_rows(raw_qubits: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """Build uniform table rows from normalized per-qubit parameter values."""
        all_params = sorted({param for qubit in raw_qubits.values() for param in qubit})
        qubits: list[dict[str, Any]] = []
        for qid in sorted(raw_qubits, key=lambda value: int(value) if value.isdigit() else value):
            row: dict[str, Any] = {"qid": qid}
            for param in all_params:
                row[param] = raw_qubits[qid].get(param)
            qubits.append(row)
        return qubits
