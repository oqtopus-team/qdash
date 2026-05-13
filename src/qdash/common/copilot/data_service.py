"""Shared Copilot data loading and tool execution helpers."""

from __future__ import annotations

import base64
import logging
import math
import statistics as stats_mod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from bunnet import SortDirection

from qdash.common.copilot.analysis_context_service import AnalysisContextBuilder
from qdash.common.copilot.heatmap_service import (
    ChipHeatmapLoader,
    TaskResultHistoryRepositoryProtocol,
)
from qdash.common.json_utils import sanitize_for_json

if TYPE_CHECKING:
    from qdash.common.copilot.analysis import AnalysisContextResult
    from qdash.common.copilot.config import CopilotConfig
    from qdash.dbmodel.calibration_note import CalibrationNoteDocument
    from qdash.dbmodel.chip import ChipDocument
    from qdash.dbmodel.coupling import CouplingDocument
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument
    from qdash.dbmodel.provenance import ParameterVersionDocument
    from qdash.dbmodel.qubit import QubitDocument
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)

MAX_FIGURE_SIZE = 5 * 1024 * 1024  # 5MB
FALLBACK_QUERY_LIMIT = 500  # Max documents to scan for manual aggregation fallback


@dataclass(frozen=True)
class _ParameterTimeseriesEntry:
    """Normalized per-document value used for chip-level parameter timeseries."""

    value: Any
    start_at: str | None


@dataclass(frozen=True)
class _LineageGraphData:
    """Normalized lineage graph payload used for LLM-friendly provenance summaries."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class _ParameterVersionRepositoryProtocol(Protocol):
    def get_current_many(self, project_id: str, keys: list[tuple[str, str]]) -> list[Any]: ...


class _ProvenanceServiceProtocol(Protocol):
    parameter_version_repo: _ParameterVersionRepositoryProtocol

    def get_lineage(self, *, project_id: str, entity_id: str, max_depth: int) -> Any: ...


def _compact_number(value: Any) -> Any:
    """Round floats to 4 significant figures to save tokens."""
    if not isinstance(value, float) or not math.isfinite(value):
        return value
    if value == 0.0:
        return 0.0
    magnitude = math.floor(math.log10(abs(value)))
    rounded = round(value, -magnitude + 3)  # 4 significant figures
    # Return int if no fractional part
    if rounded == int(rounded) and abs(rounded) < 1e15:
        return int(rounded)
    return rounded


def _compact_timestamp(iso_str: str | None) -> str:
    """Shorten ISO timestamp: '2026-02-24T02:22:04.211000' -> '02-24 02:22'."""
    if not iso_str:
        return ""
    # Take 'MM-DD HH:MM' from the ISO string
    try:
        # "2026-02-24T02:22:04" -> date="2026-02-24", time="02:22:04"
        date_part, _, time_part = iso_str.partition("T")
        month_day = date_part[5:10]  # "02-24"
        hour_min = time_part[:5]  # "02:22"
        return f"{month_day} {hour_min}"
    except (IndexError, ValueError):
        return iso_str[:16]


def _compact_output_parameters(params: dict[str, Any]) -> dict[str, Any]:
    """Compress output_parameters to {param_name: {value, unit, error}}.

    Drops verbose fields (parameter_name, qid_role, value_type, description,
    calibrated_at, execution_id, task_id) that the LLM does not need.
    """
    result: dict[str, Any] = {}
    for name, data in params.items():
        if not isinstance(data, dict):
            result[name] = data
            continue
        compact: dict[str, Any] = {"value": _compact_number(data.get("value"))}
        unit = data.get("unit")
        if unit:
            compact["unit"] = unit
        error = data.get("error")
        if error and error != 0:
            compact["error"] = _compact_number(error)
        result[name] = compact
    return result


class _CopilotDataAccess:
    """Centralized data-access adapter for shared Copilot helpers."""

    def load_latest_installed_chip(self) -> ChipDocument | None:
        from qdash.dbmodel.chip import ChipDocument

        return ChipDocument.find_one({}, sort=[("installed_at", -1)]).run()

    def load_chip(self, chip_id: str) -> ChipDocument | None:
        from qdash.dbmodel.chip import ChipDocument

        return ChipDocument.find_one({"chip_id": chip_id}).run()

    def load_qubit(self, chip_id: str, qid: str) -> QubitDocument | None:
        from qdash.dbmodel.qubit import QubitDocument

        return QubitDocument.find_one({"chip_id": chip_id, "qid": qid}).run()

    def load_coupling(self, chip_id: str, coupling_id: str) -> CouplingDocument | None:
        from qdash.dbmodel.coupling import CouplingDocument

        return CouplingDocument.find_one({"chip_id": chip_id, "qid": coupling_id}).run()

    def load_task_result(self, task_id: str) -> TaskResultHistoryDocument | None:
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        return TaskResultHistoryDocument.find_one({"task_id": task_id}).run()

    def load_completed_task_history(
        self, task_name: str, chip_id: str, qid: str, last_n: int
    ) -> list[TaskResultHistoryDocument]:
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        return cast(
            "list[TaskResultHistoryDocument]",
            TaskResultHistoryDocument.find(
                {"chip_id": chip_id, "name": task_name, "qid": qid, "status": "completed"}
            )
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n)
            .run(),
        )

    def load_parameter_versions(
        self, parameter_name: str, qid: str, chip_id: str, last_n: int
    ) -> list[ParameterVersionDocument]:
        from qdash.dbmodel.provenance import ParameterVersionDocument

        return cast(
            "list[ParameterVersionDocument]",
            ParameterVersionDocument.find(
                {"parameter_name": parameter_name, "qid": qid, "chip_id": chip_id}
            )
            .sort([("version", SortDirection.DESCENDING)])
            .limit(last_n)
            .run(),
        )

    def build_provenance_service(self) -> _ProvenanceServiceProtocol:
        from qdash.repository.provenance import (
            MongoParameterVersionRepository,
            MongoProvenanceRelationRepository,
        )

        class _ProvenanceAdapter:
            def __init__(self) -> None:
                self.parameter_version_repo = MongoParameterVersionRepository()
                self.provenance_relation_repo = MongoProvenanceRelationRepository()

            def get_lineage(self, *, project_id: str, entity_id: str, max_depth: int) -> Any:
                return self.provenance_relation_repo.get_lineage(
                    project_id=project_id,
                    entity_id=entity_id,
                    max_depth=max_depth,
                )

        return cast("_ProvenanceServiceProtocol", _ProvenanceAdapter())

    def create_task_result_history_repository(self) -> TaskResultHistoryRepositoryProtocol:
        from qdash.repository.task_result_history import MongoTaskResultHistoryRepository

        return cast("TaskResultHistoryRepositoryProtocol", MongoTaskResultHistoryRepository())

    def load_parameter_timeseries_docs(
        self, parameter_name: str, chip_id: str, qid: str, last_n: int
    ) -> list[TaskResultHistoryDocument]:
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        return cast(
            "list[TaskResultHistoryDocument]",
            TaskResultHistoryDocument.find(
                {
                    "chip_id": chip_id,
                    "qid": qid,
                    "status": "completed",
                    "output_parameter_names": parameter_name,
                }
            )
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n)
            .run(),
        )

    def load_chip_parameter_timeseries_docs(
        self, parameter_name: str, chip_id: str, last_n: int, qids: list[str] | None
    ) -> list[TaskResultHistoryDocument]:
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        query: dict[str, Any] = {
            "chip_id": chip_id,
            "status": "completed",
            "output_parameter_names": parameter_name,
        }
        if qids:
            query["qid"] = {"$in": qids}

        return cast(
            "list[TaskResultHistoryDocument]",
            TaskResultHistoryDocument.find(query)
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n * (len(qids) if qids else 200))
            .run(),
        )

    def load_qubits_for_chip(self, chip_id: str) -> list[QubitDocument]:
        from qdash.dbmodel.qubit import QubitDocument

        return cast("list[QubitDocument]", QubitDocument.find({"chip_id": chip_id}).run())

    def load_execution_history_docs(
        self, chip_id: str, status: str | None, tags: list[str] | None, last_n: int
    ) -> list[ExecutionHistoryDocument]:
        from qdash.dbmodel.execution_history import ExecutionHistoryDocument

        query: dict[str, Any] = {"chip_id": chip_id}
        if status:
            query["status"] = status
        if tags:
            query["tags"] = {"$all": tags}

        return cast(
            "list[ExecutionHistoryDocument]",
            ExecutionHistoryDocument.find(query)
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n)
            .run(),
        )

    def load_task_results(
        self,
        chip_id: str,
        task_name: str | None,
        qid: str | None,
        status: str | None,
        execution_id: str | None,
        last_n: int,
    ) -> list[TaskResultHistoryDocument]:
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        query: dict[str, Any] = {"chip_id": chip_id}
        if task_name:
            query["name"] = task_name
        if qid:
            query["qid"] = qid
        if status:
            query["status"] = status
        if execution_id:
            query["execution_id"] = execution_id

        return cast(
            "list[TaskResultHistoryDocument]",
            TaskResultHistoryDocument.find(query)
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n)
            .run(),
        )

    def load_calibration_notes(
        self, chip_id: str, execution_id: str | None, task_id: str | None, last_n: int
    ) -> list[CalibrationNoteDocument]:
        from qdash.dbmodel.calibration_note import CalibrationNoteDocument

        query: dict[str, Any] = {"chip_id": chip_id}
        if execution_id:
            query["execution_id"] = execution_id
        if task_id:
            query["task_id"] = task_id

        return cast(
            "list[CalibrationNoteDocument]",
            CalibrationNoteDocument.find(query)
            .sort([("timestamp", SortDirection.DESCENDING)])
            .limit(last_n)
            .run(),
        )

    def load_distinct_output_parameter_names(
        self, chip_id: str, qid: str | None
    ) -> list[str] | None:
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        query: dict[str, Any] = {"chip_id": chip_id, "status": "completed"}
        if qid:
            query["qid"] = qid
        collection = TaskResultHistoryDocument.get_motor_collection()
        return cast("list[str] | None", collection.distinct("output_parameter_names", query))

    def load_output_parameter_name_fallback_docs(
        self, chip_id: str, qid: str | None
    ) -> list[TaskResultHistoryDocument]:
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        query: dict[str, Any] = {"chip_id": chip_id, "status": "completed"}
        if qid:
            query["qid"] = qid
        return cast(
            "list[TaskResultHistoryDocument]",
            TaskResultHistoryDocument.find(query).limit(FALLBACK_QUERY_LIMIT).run(),
        )


class CopilotDataService:
    """Service for loading data used by the Copilot AI assistant."""

    def __init__(self, data_access: _CopilotDataAccess | None = None) -> None:
        self._data_access = data_access or _CopilotDataAccess()
        self._analysis_context_builder = AnalysisContextBuilder(
            load_qubit_params=self._analysis_load_qubit_params,
            load_task_result=self._analysis_load_task_result,
            load_task_history=self._analysis_load_task_history,
            load_neighbor_qubit_params=self._analysis_load_neighbor_qubit_params,
            load_coupling_params=self._analysis_load_coupling_params,
            load_figure_as_base64=self._analysis_load_figure_as_base64,
            collect_expected_images=self._analysis_collect_expected_images,
        )
        self._heatmap_loader = ChipHeatmapLoader(
            data_access=self._data_access,
            compact_number=_compact_number,
        )

    def _analysis_load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]:
        """Forward qubit-param lookup for analysis context assembly."""
        return self.load_qubit_params(chip_id, qid)

    def _analysis_load_task_result(self, task_id: str) -> dict[str, Any] | None:
        """Forward task-result lookup for analysis context assembly."""
        return self.load_task_result(task_id)

    def _analysis_load_task_history(
        self,
        task_name: str,
        chip_id: str,
        qid: str,
        last_n: int,
    ) -> list[dict[str, Any]]:
        """Forward task-history lookup for analysis context assembly."""
        return self.load_task_history(task_name, chip_id, qid, last_n)

    def _analysis_load_neighbor_qubit_params(
        self,
        chip_id: str,
        qid: str,
        params: list[str] | None,
    ) -> dict[str, dict[str, Any]]:
        """Forward neighbor-qubit lookup for analysis context assembly."""
        return self.load_neighbor_qubit_params(chip_id, qid, params or [])

    def _analysis_load_coupling_params(
        self,
        chip_id: str,
        qid: str,
        params: list[str] | None,
    ) -> dict[str, dict[str, Any]]:
        """Forward coupling lookup for analysis context assembly."""
        return self.load_coupling_params(chip_id, qid, params or [])

    def _analysis_load_figure_as_base64(self, figure_paths: list[str]) -> str | None:
        """Forward figure loading for analysis context assembly."""
        return self.load_figure_as_base64(figure_paths)

    def _analysis_collect_expected_images(
        self,
        knowledge: Any,
        max_images: int | None,
    ) -> list[tuple[str, str]]:
        """Forward expected-image lookup for analysis context assembly."""
        return self.collect_expected_images(knowledge, max_images=max_images)

    def load_default_chip_id(self) -> str | None:
        """Load the most recently installed chip_id from DB."""
        doc = self._data_access.load_latest_installed_chip()
        if doc is None:
            return None
        return str(doc.chip_id)

    def load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]:
        """Load current qubit parameters from DB."""
        doc = self._data_access.load_qubit(chip_id, qid)
        if doc is None:
            return {}
        result: dict[str, Any] = sanitize_for_json(dict(doc.data))
        return result

    def load_task_result(self, task_id: str) -> dict[str, Any] | None:
        """Load task result from DB."""
        doc = self._data_access.load_task_result(task_id)
        if doc is None:
            return None
        return {
            "input_parameters": doc.input_parameters or {},
            "output_parameters": doc.output_parameters or {},
            "run_parameters": getattr(doc, "run_parameters", {}) or {},
            "figure_path": getattr(doc, "figure_path", []) or [],
        }

    def load_figure_as_base64(self, figure_paths: list[str]) -> str | None:
        """Read the first existing PNG file from figure_paths and return base64."""
        for fp in figure_paths:
            p = Path(fp)
            if p.is_file() and p.suffix.lower() == ".png":
                if p.stat().st_size > MAX_FIGURE_SIZE:
                    logger.warning("Figure %s exceeds 5MB size limit, skipping", fp)
                    continue
                return base64.b64encode(p.read_bytes()).decode("ascii")
        return None

    def collect_expected_images(
        self,
        knowledge: Any,
        max_images: int | None = None,
    ) -> list[tuple[str, str]]:
        """Collect expected reference images from TaskKnowledge.

        Returns list of (base64_data, alt_text) for images with embedded data.
        Includes both task-level images and case-level images.
        """
        if knowledge is None:
            return []
        result = [(img.base64_data, img.alt_text) for img in knowledge.images if img.base64_data]
        for case in knowledge.cases:
            for img in case.images:
                if img.base64_data:
                    result.append((img.base64_data, f"[Case: {case.title}] {img.alt_text}"))
        if max_images is not None and max_images >= 0:
            return result[:max_images]
        return result

    def load_task_history(
        self, task_name: str, chip_id: str, qid: str, last_n: int = 5
    ) -> list[dict[str, Any]]:
        """Load recent completed results for the same task+qubit."""
        docs = self._data_access.load_completed_task_history(task_name, chip_id, qid, last_n)
        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(
                {
                    "output_parameters": _compact_output_parameters(doc.output_parameters or {}),
                    "start_at": _compact_timestamp(
                        doc.start_at.isoformat() if doc.start_at else None
                    ),
                    "execution_id": doc.execution_id,
                }
            )
        return results

    def load_neighbor_qubit_params(
        self, chip_id: str, qid: str, param_names: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Load specified parameters from neighboring qubits via topology."""
        chip = self._data_access.load_chip(chip_id)
        if chip is None or chip.topology_id is None:
            return {}

        from qdash.common.topology_config import load_topology

        topology = load_topology(chip.topology_id)

        # Find neighbor qubit IDs from coupling pairs
        try:
            qid_int = int(qid)
        except ValueError:
            return {}

        neighbors: set[int] = set()
        for q1, q2 in topology.couplings:
            if q1 == qid_int:
                neighbors.add(q2)
            elif q2 == qid_int:
                neighbors.add(q1)

        result: dict[str, dict[str, Any]] = {}
        for neighbor_id in sorted(neighbors):
            neighbor_qid = str(neighbor_id)
            doc = self._data_access.load_qubit(chip_id, neighbor_qid)
            if doc is None:
                continue
            params: dict[str, Any] = {}
            for name in param_names:
                if name in doc.data:
                    params[name] = doc.data[name]
            if params:
                result[neighbor_qid] = params
        return result

    def load_coupling_params(
        self, chip_id: str, qid: str, param_names: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Load specified parameters from couplings related to the target qubit."""
        # If qid contains "-", it's already a coupling ID
        if "-" in qid:
            coupling_ids = [qid]
        else:
            # Find related couplings via topology
            chip = self._data_access.load_chip(chip_id)
            if chip is None or chip.topology_id is None:
                return {}

            from qdash.common.topology_config import load_topology

            topology = load_topology(chip.topology_id)

            try:
                qid_int = int(qid)
            except ValueError:
                return {}

            coupling_ids = []
            for q1, q2 in topology.couplings:
                if q1 == qid_int or q2 == qid_int:
                    coupling_ids.append(f"{q1}-{q2}")

        result: dict[str, dict[str, Any]] = {}
        for coupling_id in coupling_ids:
            doc = self._data_access.load_coupling(chip_id, coupling_id)
            if doc is None:
                continue
            params: dict[str, Any] = {}
            for name in param_names:
                if name in doc.data:
                    params[name] = doc.data[name]
            if params:
                result[coupling_id] = params
        return result

    def load_latest_task_result(self, task_name: str, chip_id: str, qid: str) -> dict[str, Any]:
        """Load the latest completed result for a task+qubit."""
        results = self.load_task_history(task_name, chip_id, qid, last_n=1)
        return results[0] if results else {"error": "No results found"}

    def load_parameter_timeseries(
        self, parameter_name: str, chip_id: str, qid: str, last_n: int = 10
    ) -> list[dict[str, Any]]:
        """Load time series data for a specific output parameter by name.

        Queries task_result_history by output_parameter_names field,
        which is indexed and allows parameter-name-based lookups
        regardless of task name.
        """
        docs = self._data_access.load_parameter_timeseries_docs(
            parameter_name, chip_id, qid, last_n
        )

        results: list[dict[str, Any]] = []
        for doc in reversed(docs):  # chronological order (oldest first)
            param_data = (doc.output_parameters or {}).get(parameter_name)
            if param_data is None:
                continue
            entry: dict[str, Any] = {
                "start_at": doc.start_at.isoformat() if doc.start_at else None,
                "execution_id": doc.execution_id,
                "task_name": doc.name,
            }
            if isinstance(param_data, dict):
                entry["value"] = param_data.get("value")
                entry["unit"] = param_data.get("unit", "")
                entry["calibrated_at"] = param_data.get("calibrated_at")
            else:
                entry["value"] = param_data
                entry["unit"] = ""
            results.append(entry)

        if not results:
            return [{"error": f"No results found for parameter '{parameter_name}' on qid={qid}"}]
        return results

    def load_chip_parameter_timeseries(
        self,
        parameter_name: str,
        chip_id: str,
        last_n: int = 10,
        qids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Load per-qubit timeseries and summary for a parameter.

        Single DB query replaces N individual get_parameter_timeseries calls.
        Returns per-qubit timeseries (value + timestamp), stats, trend,
        and chip-wide statistics — enough data for charts and tables.

        Parameters
        ----------
        qids : list[str] | None
            Optional list of qubit IDs to fetch. If None, fetches all qubits.
        """
        docs = self._data_access.load_chip_parameter_timeseries_docs(
            parameter_name, chip_id, last_n, qids
        )
        per_qubit, unit = self._group_chip_parameter_timeseries(docs, parameter_name)
        if not per_qubit:
            return {"error": f"No data for '{parameter_name}' on chip '{chip_id}'"}

        qubits, timeseries, latest_values = self._summarize_chip_parameter_timeseries(
            per_qubit, last_n
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
    ) -> tuple[dict[str, list[_ParameterTimeseriesEntry]], str]:
        """Group parameter timeseries documents by qid and normalize their values."""
        from collections import defaultdict

        per_qubit: dict[str, list[_ParameterTimeseriesEntry]] = defaultdict(list)
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
                _ParameterTimeseriesEntry(
                    value=value,
                    start_at=doc.start_at.isoformat() if doc.start_at else None,
                )
            )
        return dict(per_qubit), unit

    def _summarize_chip_parameter_timeseries(
        self,
        per_qubit: dict[str, list[_ParameterTimeseriesEntry]],
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
        entries: list[_ParameterTimeseriesEntry],
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
            "latest": _compact_number(latest),
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
            qubit_summary["min"] = _compact_number(min(numeric_values))
            qubit_summary["max"] = _compact_number(max(numeric_values))
            qubit_summary["mean"] = _compact_number(stats_mod.mean(numeric_values))
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

    @staticmethod
    def _build_chip_parameter_statistics(latest_values: list[float]) -> dict[str, Any]:
        """Build chip-wide statistics from the latest numeric value per qubit."""
        chip_stats: dict[str, Any] = {
            "count": len(latest_values),
            "mean": _compact_number(stats_mod.mean(latest_values)) if latest_values else 0,
            "median": _compact_number(stats_mod.median(latest_values)) if latest_values else 0,
            "min": _compact_number(min(latest_values)) if latest_values else 0,
            "max": _compact_number(max(latest_values)) if latest_values else 0,
        }
        if len(latest_values) >= 2:
            chip_stats["stdev"] = _compact_number(stats_mod.stdev(latest_values))
        return chip_stats

    def load_chip_summary(
        self, chip_id: str, param_names: list[str] | None = None
    ) -> dict[str, Any]:
        """Load summary of all qubits on a chip with computed statistics.

        Returns statistics (always included) and a list-of-dicts ``qubits``
        table.
        """
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

    @staticmethod
    def _build_chip_summary_statistics(
        numeric_values: dict[str, list[float]],
    ) -> dict[str, dict[str, float]]:
        """Build per-parameter descriptive statistics for a chip summary."""
        statistics: dict[str, dict[str, float]] = {}
        for key, values in numeric_values.items():
            if len(values) >= 2:
                statistics[key] = {
                    "mean": _compact_number(stats_mod.mean(values)),
                    "median": _compact_number(stats_mod.median(values)),
                    "stdev": _compact_number(stats_mod.stdev(values)),
                    "min": _compact_number(min(values)),
                    "max": _compact_number(max(values)),
                    "count": len(values),
                }
            elif len(values) == 1:
                statistics[key] = {
                    "mean": _compact_number(values[0]),
                    "median": _compact_number(values[0]),
                    "stdev": 0.0,
                    "min": _compact_number(values[0]),
                    "max": _compact_number(values[0]),
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

    def load_coupling_params_tool(
        self,
        chip_id: str,
        coupling_id: str | None = None,
        qubit_id: str | None = None,
        param_names: list[str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Load coupling parameters by coupling_id or qubit_id."""
        if coupling_id:
            coupling_ids = [coupling_id]
        elif qubit_id:
            chip = self._data_access.load_chip(chip_id)
            if chip is None or chip.topology_id is None:
                return {"error": f"Chip {chip_id} not found or has no topology"}

            from qdash.common.topology_config import load_topology

            topology = load_topology(chip.topology_id)
            try:
                qid_int = int(qubit_id)
            except ValueError:
                return {"error": f"Invalid qubit_id: {qubit_id}"}

            coupling_ids = []
            for q1, q2 in topology.couplings:
                if q1 == qid_int or q2 == qid_int:
                    coupling_ids.append(f"{q1}-{q2}")
        else:
            return {"error": "Either coupling_id or qubit_id must be provided"}

        results: list[dict[str, Any]] = []
        for cid in coupling_ids:
            doc = self._data_access.load_coupling(chip_id, cid)
            if doc is None:
                continue
            data = dict(doc.data)
            if param_names:
                data = {k: v for k, v in data.items() if k in param_names}
            results.append({"coupling_id": cid, "data": sanitize_for_json(data)})

        if not results:
            return {"error": "No coupling data found"}
        return results

    def load_execution_history(
        self,
        chip_id: str,
        status: str | None = None,
        tags: list[str] | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Load recent execution history for a chip."""
        docs = self._data_access.load_execution_history_docs(chip_id, status, tags, last_n)

        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(
                {
                    "execution_id": doc.execution_id,
                    "name": doc.name,
                    "status": doc.status,
                    "chip_id": doc.chip_id,
                    "tags": doc.tags,
                    "start_at": _compact_timestamp(
                        doc.start_at.isoformat() if doc.start_at else None
                    ),
                    "end_at": _compact_timestamp(doc.end_at.isoformat() if doc.end_at else None),
                    "elapsed_time": _compact_number(doc.elapsed_time),
                    "message": doc.message,
                }
            )

        if not results:
            return [{"error": f"No executions found for chip_id={chip_id}"}]
        return results

    def load_compare_qubits(
        self, chip_id: str, qids: list[str], param_names: list[str] | None = None
    ) -> dict[str, Any]:
        """Load and compare parameters across multiple qubits.

        Returns compact {qid: {param: value}} with values only (no unit/description).
        """
        comparison: dict[str, dict[str, Any]] = {}
        for qid in qids:
            doc = self._data_access.load_qubit(chip_id, qid)
            if doc is None:
                comparison[qid] = {"error": f"Qubit {qid} not found"}
                continue
            data = dict(doc.data)
            if param_names:
                data = {k: v for k, v in data.items() if k in param_names}
            # Extract compact {param: value} per qubit (same as load_chip_summary)
            compact: dict[str, Any] = {}
            for key, val in data.items():
                raw = val.get("value") if isinstance(val, dict) and "value" in val else val
                compact[key] = _compact_number(raw) if isinstance(raw, (int, float)) else raw
            comparison[qid] = compact

        return {"chip_id": chip_id, "qubits": comparison}

    def load_chip_topology(self, chip_id: str) -> dict[str, Any]:
        """Load chip topology information."""
        chip = self._data_access.load_chip(chip_id)
        if chip is None:
            return {"error": f"Chip {chip_id} not found"}
        if chip.topology_id is None:
            return {"error": f"Chip {chip_id} has no topology configured"}

        from qdash.common.topology_config import load_topology

        topology = load_topology(chip.topology_id)

        qubit_positions = {
            str(qid): {"row": pos.row, "col": pos.col} for qid, pos in topology.qubits.items()
        }
        couplings = [[q1, q2] for q1, q2 in topology.couplings]

        return {
            "chip_id": chip_id,
            "topology_id": chip.topology_id,
            "grid_size": topology.grid_size,
            "num_qubits": topology.num_qubits,
            "layout_type": topology.layout_type,
            "qubit_positions": qubit_positions,
            "couplings": couplings,
        }

    def load_search_task_results(
        self,
        chip_id: str,
        task_name: str | None = None,
        qid: str | None = None,
        status: str | None = None,
        execution_id: str | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Search task result history with flexible filters."""
        docs = self._data_access.load_task_results(
            chip_id, task_name, qid, status, execution_id, last_n
        )

        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(
                {
                    "task_id": doc.task_id,
                    "task_name": doc.name,
                    "qid": doc.qid,
                    "status": doc.status,
                    "execution_id": doc.execution_id,
                    "start_at": _compact_timestamp(
                        doc.start_at.isoformat() if doc.start_at else None
                    ),
                    "end_at": _compact_timestamp(doc.end_at.isoformat() if doc.end_at else None),
                    "elapsed_time": _compact_number(doc.elapsed_time),
                    "output_parameters": _compact_output_parameters(doc.output_parameters or {}),
                    "message": doc.message,
                }
            )

        if not results:
            return [{"error": "No task results found matching the filters"}]
        return results

    def load_calibration_notes(
        self,
        chip_id: str,
        execution_id: str | None = None,
        task_id: str | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Load calibration notes for a chip."""
        docs = self._data_access.load_calibration_notes(chip_id, execution_id, task_id, last_n)

        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(
                {
                    "execution_id": doc.execution_id,
                    "task_id": doc.task_id,
                    "note": doc.note,
                    "timestamp": doc.timestamp.isoformat() if doc.timestamp else None,
                }
            )

        if not results:
            return [{"error": f"No calibration notes found for chip_id={chip_id}"}]
        return results

    def _resolve_project_id(self, chip_id: str) -> str | None:
        """Resolve project_id from chip_id via ChipDocument."""
        doc = self._data_access.load_chip(chip_id)
        if doc is None:
            return None
        return str(doc.project_id)

    @staticmethod
    def _compute_graph_depths(
        *,
        origin_id: str,
        edges: list[dict[str, str]],
        reverse: bool,
    ) -> dict[str, int]:
        """Compute shortest-path depths from origin using graph edges."""
        from collections import defaultdict, deque

        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if reverse:
                adjacency[edge["target"]].append(edge["source"])
            else:
                adjacency[edge["source"]].append(edge["target"])

        depths: dict[str, int] = {origin_id: 0}
        queue: deque[str] = deque([origin_id])

        while queue:
            current = queue.popleft()
            current_depth = depths[current]
            for nxt in adjacency.get(current, []):
                if nxt in depths:
                    continue
                depths[nxt] = current_depth + 1
                queue.append(nxt)

        return depths

    def _get_provenance_service(self) -> _ProvenanceServiceProtocol:
        """Build a lightweight provenance adapter for lineage lookups."""
        return self._data_access.build_provenance_service()

    def load_provenance_lineage_graph(
        self, entity_id: str, chip_id: str, max_depth: int = 5
    ) -> dict[str, Any]:
        """Load the provenance lineage graph and return an LLM-friendly summary."""
        # Validate entity_id format: parameter_name:qid:execution_id:task_id
        if not entity_id or entity_id.count(":") != 3:
            return {
                "error": (
                    f"Invalid entity_id format: '{entity_id}'. "
                    "Expected 'parameter_name:qid:execution_id:task_id'."
                )
            }

        # Clamp max_depth to service limits
        max_depth = max(1, min(max_depth, 20))

        project_id = self._resolve_project_id(chip_id)
        if project_id is None:
            return {
                "error": (
                    f"Unable to resolve project for chip '{chip_id}'. "
                    "The chip may not exist or may not be associated with a project."
                )
            }

        service = self._get_provenance_service()
        lineage_data = service.get_lineage(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )
        parameter_version_repo = service.parameter_version_repo
        normalized_graph = self._normalize_lineage_graph_data(lineage_data)
        nodes = self._build_lineage_graph_nodes(normalized_graph.nodes)
        edges = self._build_lineage_graph_edges(normalized_graph.edges)
        depths = self._compute_graph_depths(origin_id=entity_id, edges=edges, reverse=False)
        for node in nodes:
            node["depth"] = depths.get(node["id"], 0)

        self._enrich_lineage_graph_node_versions(nodes, parameter_version_repo, project_id)

        return {
            "origin": entity_id,
            "num_nodes": len(nodes),
            "num_edges": len(edges),
            "max_depth": max_depth,
            "nodes": nodes,
            "edges": edges,
        }

    def _normalize_lineage_graph_data(self, lineage_data: Any) -> _LineageGraphData:
        """Convert lineage service output into a uniform dict-backed graph payload."""
        if isinstance(lineage_data, dict):
            return _LineageGraphData(
                nodes=list(lineage_data.get("nodes", [])),
                edges=list(lineage_data.get("edges", [])),
            )

        return _LineageGraphData(
            nodes=[
                {
                    "id": getattr(node, "node_id", ""),
                    "type": getattr(node, "node_type", "entity"),
                    "metadata": self._build_lineage_node_metadata(node),
                }
                for node in getattr(lineage_data, "nodes", [])
            ],
            edges=[
                {
                    "source": getattr(edge, "source_id", ""),
                    "target": getattr(edge, "target_id", ""),
                    "relation_type": getattr(edge, "relation_type", ""),
                }
                for edge in getattr(lineage_data, "edges", [])
            ],
        )

    @staticmethod
    def _build_lineage_node_metadata(node: Any) -> dict[str, Any]:
        """Build a metadata dict from a lineage node object."""
        entity = getattr(node, "entity", None)
        activity = getattr(node, "activity", None)
        return {
            "parameter_name": getattr(entity, "parameter_name", None),
            "qid": getattr(entity, "qid", None),
            "value": getattr(entity, "value", None),
            "unit": getattr(entity, "unit", None),
            "version": getattr(entity, "version", None),
            "task_name": getattr(entity, "task_name", None) or getattr(activity, "task_name", None),
            "execution_id": getattr(entity, "execution_id", None)
            or getattr(activity, "execution_id", None),
            "valid_from": getattr(entity, "valid_from", None),
            "status": getattr(activity, "status", None),
            "latest_version": getattr(node, "latest_version", None),
        }

    def _build_lineage_graph_nodes(self, raw_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert normalized lineage nodes into uniform LLM-friendly node dicts."""
        nodes: list[dict[str, Any]] = []
        for node_dict in raw_nodes:
            metadata = node_dict.get("metadata", {})
            node_type = node_dict.get("type", "entity")
            nodes.append(
                {
                    "type": node_type,
                    "id": str(node_dict.get("id", "")),
                    "depth": 0,
                    "param": self._extract_lineage_node_param(metadata, node_type),
                    "qid": self._extract_lineage_node_qid(metadata, node_type),
                    "value": self._extract_lineage_node_value(metadata, node_type),
                    "unit": self._extract_lineage_node_unit(metadata, node_type),
                    "ver": self._extract_lineage_node_version(metadata, node_type),
                    "task": self._extract_lineage_node_task(metadata, node_type),
                    "exec_id": self._extract_lineage_node_execution_id(metadata, node_type),
                    "valid_from": self._extract_lineage_node_valid_from(metadata, node_type),
                    "status": self._extract_lineage_node_status(metadata, node_type),
                }
            )
        return nodes

    @staticmethod
    def _build_lineage_graph_edges(raw_edges: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Convert normalized lineage edges into the compact graph representation."""
        return [
            {
                "relation": str(edge.get("relation_type", "")),
                "source": str(edge.get("source", "")),
                "target": str(edge.get("target", "")),
            }
            for edge in raw_edges
        ]

    @staticmethod
    def _extract_lineage_node_param(metadata: dict[str, Any], node_type: str) -> str | None:
        return metadata.get("parameter_name") or None if node_type == "entity" else None

    @staticmethod
    def _extract_lineage_node_qid(metadata: dict[str, Any], node_type: str) -> str | None:
        if node_type not in {"entity", "activity"}:
            return None
        return metadata.get("qid") or None

    @staticmethod
    def _extract_lineage_node_value(metadata: dict[str, Any], node_type: str) -> Any:
        if node_type != "entity":
            return None
        raw_value = metadata.get("value")
        return _compact_number(raw_value) if raw_value is not None else None

    @staticmethod
    def _extract_lineage_node_unit(metadata: dict[str, Any], node_type: str) -> str | None:
        return metadata.get("unit") or None if node_type == "entity" else None

    @staticmethod
    def _extract_lineage_node_version(metadata: dict[str, Any], node_type: str) -> int | str | None:
        if node_type != "entity":
            return None
        version = metadata.get("version")
        latest_version = metadata.get("latest_version")
        if latest_version is not None and version is not None:
            return f"{version}/{latest_version}"
        return version

    @staticmethod
    def _extract_lineage_node_task(metadata: dict[str, Any], node_type: str) -> str | None:
        return metadata.get("task_name") or None if node_type in {"entity", "activity"} else None

    @staticmethod
    def _extract_lineage_node_execution_id(
        metadata: dict[str, Any],
        node_type: str,
    ) -> str | None:
        return metadata.get("execution_id") or None if node_type in {"entity", "activity"} else None

    @staticmethod
    def _extract_lineage_node_valid_from(
        metadata: dict[str, Any],
        node_type: str,
    ) -> str | None:
        if node_type != "entity" or not metadata.get("valid_from"):
            return None
        return _compact_timestamp(str(metadata["valid_from"]))

    @staticmethod
    def _extract_lineage_node_status(metadata: dict[str, Any], node_type: str) -> str | None:
        return metadata.get("status") or None if node_type == "activity" else None

    def _enrich_lineage_graph_node_versions(
        self,
        nodes: list[dict[str, Any]],
        parameter_version_repo: _ParameterVersionRepositoryProtocol,
        project_id: str,
    ) -> None:
        """Append current versions to stale entity nodes in the lineage graph."""
        entity_keys = sorted(
            {
                (str(node["param"]), str(node["qid"]))
                for node in nodes
                if node["type"] == "entity" and node["param"] and node["qid"]
            }
        )
        current_versions = parameter_version_repo.get_current_many(project_id, keys=entity_keys)
        current_version_map = {
            (doc.parameter_name, getattr(doc, "qid", "")): getattr(doc, "version", 1)
            for doc in current_versions
        }
        for node in nodes:
            if node["type"] != "entity" or node["param"] is None or node["qid"] is None:
                continue
            current_ver = current_version_map.get((str(node["param"]), str(node["qid"])))
            current_node_ver = node["ver"]
            if (
                current_ver is not None
                and isinstance(current_node_ver, int)
                and current_ver > current_node_ver
            ):
                node["ver"] = f"{current_node_ver}/{current_ver}"

    def load_parameter_lineage(
        self, parameter_name: str, qid: str, chip_id: str, last_n: int = 10
    ) -> list[dict[str, Any]]:
        """Load version history for a specific parameter."""
        docs = self._data_access.load_parameter_versions(parameter_name, qid, chip_id, last_n)

        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(
                {
                    "version": doc.version,
                    "value": _compact_number(doc.value),
                    "unit": doc.unit,
                    "error": _compact_number(doc.error) if doc.error else None,
                    "execution_id": doc.execution_id,
                    "task_id": doc.task_id,
                    "task_name": doc.task_name,
                    "valid_from": _compact_timestamp(
                        doc.valid_from.isoformat() if doc.valid_from else None
                    ),
                    "valid_until": _compact_timestamp(
                        doc.valid_until.isoformat() if doc.valid_until else None
                    ),
                }
            )

        if not results:
            return [
                {
                    "error": (
                        f"No version history found for parameter '{parameter_name}' "
                        f"on qid={qid}, chip_id={chip_id}"
                    )
                }
            ]
        return results

    def load_chip_heatmap(
        self,
        chip_id: str,
        metric_name: str,
        selection_mode: str = "latest",
        within_hours: int | None = None,
    ) -> dict[str, Any]:
        """Generate a chip-wide heatmap for a qubit metric.

        Returns a Plotly figure dict suitable for the chat UI.
        """
        return self._heatmap_loader.load_chip_heatmap(
            chip_id=chip_id,
            metric_name=metric_name,
            selection_mode=selection_mode,
            within_hours=within_hours,
        )

    def load_available_parameters(
        self,
        chip_id: str,
        qid: str | None = None,
    ) -> dict[str, Any]:
        """List distinct output parameter names recorded for a chip."""
        try:
            names = self._data_access.load_distinct_output_parameter_names(chip_id, qid)
        except (AttributeError, TypeError) as e:
            # Fallback: manual aggregation when distinct() is unavailable
            logger.warning("distinct() failed for output_parameter_names: %s", e)
            docs = self._data_access.load_output_parameter_name_fallback_docs(chip_id, qid)
            name_set: set[str] = set()
            for doc in docs:
                if doc.output_parameter_names:
                    name_set.update(doc.output_parameter_names)
            names = sorted(name_set)

        if not names:
            return {
                "error": f"No output parameters found for chip_id={chip_id}"
                + (f", qid={qid}" if qid else "")
            }

        return {
            "chip_id": chip_id,
            "qid": qid,
            "parameter_names": sorted(names),
            "count": len(names),
        }

    def build_analysis_context(
        self,
        task_name: str,
        chip_id: str,
        qid: str,
        task_id: str,
        image_base64: str | None,
        config: CopilotConfig,
    ) -> AnalysisContextResult:
        """Build a full analysis context from DB data and TaskKnowledge.

        Consolidates the duplicated context-building logic that was
        previously inlined in both ``analyze_task_result`` and
        ``analyze_task_result_stream``.
        """
        return self._analysis_context_builder.build_analysis_context(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
            task_id=task_id,
            image_base64=image_base64,
            config=config,
        )

    @staticmethod
    def build_images_sent_metadata(
        image_base64: str | None,
        figure_paths: list[str],
        expected_images: list[tuple[str, str]],
        task_name: str,
    ) -> dict[str, Any]:
        """Build the ``images_sent`` metadata dict for analysis responses."""
        return {
            "experiment_figure": bool(image_base64),
            "experiment_figure_paths": figure_paths if image_base64 else [],
            "expected_images": [
                {"alt_text": alt, "index": i} for i, (_, alt) in enumerate(expected_images)
            ],
            "task_name": task_name,
        }

    def build_tool_executors(self) -> dict[str, Any]:
        """Build the tool executor mapping for LLM function calling.

        Note: ``execute_python_analysis`` is overridden by ``_wrap_tool_executors``
        in ``copilot_agent.py`` to auto-inject the data_store.
        """
        from qdash.common.copilot.sandbox import execute_python_analysis

        return (
            self._build_qubit_analysis_tool_executors()
            | self._build_chip_overview_tool_executors()
            | self._build_history_and_provenance_tool_executors()
            | {"execute_python_analysis": lambda args: execute_python_analysis(args["code"])}
        )

    def _build_qubit_analysis_tool_executors(self) -> dict[str, Any]:
        """Build tool executors for task-result and qubit-level analysis lookups."""
        return {
            "get_qubit_params": lambda args: self.load_qubit_params(args["chip_id"], args["qid"]),
            "get_latest_task_result": lambda args: self.load_latest_task_result(
                args["task_name"], args["chip_id"], args["qid"]
            ),
            "get_task_history": lambda args: self.load_task_history(
                args["task_name"], args["chip_id"], args["qid"], args.get("last_n", 5)
            ),
            "get_parameter_timeseries": lambda args: self.load_parameter_timeseries(
                args["parameter_name"], args["chip_id"], args["qid"], args.get("last_n", 10)
            ),
            "compare_qubits": lambda args: self.load_compare_qubits(
                args["chip_id"], args["qids"], args.get("param_names")
            ),
            "get_coupling_params": lambda args: self.load_coupling_params_tool(
                args["chip_id"],
                args.get("coupling_id"),
                args.get("qubit_id"),
                args.get("param_names"),
            ),
        }

    def _build_chip_overview_tool_executors(self) -> dict[str, Any]:
        """Build tool executors for chip summaries, topology, and metric overviews."""
        return {
            "get_chip_summary": lambda args: self.load_chip_summary(
                args["chip_id"], args.get("param_names")
            ),
            "get_chip_topology": lambda args: self.load_chip_topology(args["chip_id"]),
            "generate_chip_heatmap": lambda args: self.load_chip_heatmap(
                args["chip_id"],
                args["metric_name"],
                args.get("selection_mode", "latest"),
                args.get("within_hours"),
            ),
            "list_available_parameters": lambda args: self.load_available_parameters(
                args["chip_id"], args.get("qid")
            ),
            "get_chip_parameter_timeseries": lambda args: self.load_chip_parameter_timeseries(
                args["parameter_name"],
                args["chip_id"],
                args.get("last_n", 10),
                args.get("qids"),
            ),
        }

    def _build_history_and_provenance_tool_executors(self) -> dict[str, Any]:
        """Build tool executors for execution history, notes, and provenance lookups."""
        return {
            "get_execution_history": lambda args: self.load_execution_history(
                args["chip_id"], args.get("status"), args.get("tags"), args.get("last_n", 10)
            ),
            "search_task_results": lambda args: self.load_search_task_results(
                args["chip_id"],
                args.get("task_name"),
                args.get("qid"),
                args.get("status"),
                args.get("execution_id"),
                args.get("last_n", 10),
            ),
            "get_calibration_notes": lambda args: self.load_calibration_notes(
                args["chip_id"],
                args.get("execution_id"),
                args.get("task_id"),
                args.get("last_n", 10),
            ),
            "get_parameter_lineage": lambda args: self.load_parameter_lineage(
                args["parameter_name"], args["qid"], args["chip_id"], args.get("last_n", 10)
            ),
            "get_provenance_lineage_graph": lambda args: self.load_provenance_lineage_graph(
                args["entity_id"], args["chip_id"], args.get("max_depth", 5)
            ),
        }
