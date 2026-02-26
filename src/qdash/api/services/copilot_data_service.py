"""Copilot data service for QDash API.

Provides data loading and tool execution for the Copilot AI assistant.
"""

from __future__ import annotations

import base64
import logging
import math
import statistics as stats_mod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bunnet import SortDirection
from qdash.api.lib.json_utils import sanitize_for_json

if TYPE_CHECKING:
    from qdash.api.lib.copilot_analysis import AnalysisContextResult
    from qdash.api.lib.copilot_config import CopilotConfig

logger = logging.getLogger(__name__)

MAX_FIGURE_SIZE = 5 * 1024 * 1024  # 5MB
FALLBACK_QUERY_LIMIT = 500  # Max documents to scan for manual aggregation fallback


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


class CopilotDataService:
    """Service for loading data used by the Copilot AI assistant."""

    def load_default_chip_id(self) -> str | None:
        """Load the most recently installed chip_id from DB."""
        from qdash.dbmodel.chip import ChipDocument

        doc = ChipDocument.find_one({}, sort=[("installed_at", -1)]).run()
        if doc is None:
            return None
        return str(doc.chip_id)

    def load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]:
        """Load current qubit parameters from DB."""
        from qdash.dbmodel.qubit import QubitDocument

        doc = QubitDocument.find_one({"chip_id": chip_id, "qid": qid}).run()
        if doc is None:
            return {}
        result: dict[str, Any] = sanitize_for_json(dict(doc.data))
        return result

    def load_task_result(self, task_id: str) -> dict[str, Any] | None:
        """Load task result from DB."""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        doc = TaskResultHistoryDocument.find_one({"task_id": task_id}).run()
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
        return result

    def load_task_history(
        self, task_name: str, chip_id: str, qid: str, last_n: int = 5
    ) -> list[dict[str, Any]]:
        """Load recent completed results for the same task+qubit."""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        docs = (
            TaskResultHistoryDocument.find(
                {"chip_id": chip_id, "name": task_name, "qid": qid, "status": "completed"}
            )
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n)
            .run()
        )
        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(
                {
                    "output_parameters": doc.output_parameters or {},
                    "start_at": doc.start_at.isoformat() if doc.start_at else None,
                    "execution_id": doc.execution_id,
                }
            )
        return results

    def load_neighbor_qubit_params(
        self, chip_id: str, qid: str, param_names: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Load specified parameters from neighboring qubits via topology."""
        from qdash.dbmodel.chip import ChipDocument
        from qdash.dbmodel.qubit import QubitDocument

        chip = ChipDocument.find_one({"chip_id": chip_id}).run()
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
            doc = QubitDocument.find_one({"chip_id": chip_id, "qid": neighbor_qid}).run()
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
        from qdash.dbmodel.coupling import CouplingDocument

        # If qid contains "-", it's already a coupling ID
        if "-" in qid:
            coupling_ids = [qid]
        else:
            # Find related couplings via topology
            from qdash.dbmodel.chip import ChipDocument

            chip = ChipDocument.find_one({"chip_id": chip_id}).run()
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
            doc = CouplingDocument.find_one({"chip_id": chip_id, "qid": coupling_id}).run()
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
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        docs = (
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
            .run()
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
        from collections import defaultdict

        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        query: dict[str, Any] = {
            "chip_id": chip_id,
            "status": "completed",
            "output_parameter_names": parameter_name,
        }
        if qids:
            query["qid"] = {"$in": qids}

        docs = (
            TaskResultHistoryDocument.find(query)
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n * (len(qids) if qids else 200))
            .run()
        )

        # Group by qid
        per_qubit: dict[str, list[dict[str, Any]]] = defaultdict(list)
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
            if value is not None:
                per_qubit[doc.qid].append(
                    {
                        "value": value,
                        "start_at": doc.start_at.isoformat() if doc.start_at else None,
                    }
                )

        if not per_qubit:
            return {"error": f"No data for '{parameter_name}' on chip '{chip_id}'"}

        # Build per-qubit data with timeseries + stats
        qubits: dict[str, dict[str, Any]] = {}
        all_latest: list[float] = []

        for qid, entries in sorted(
            per_qubit.items(),
            key=lambda x: int(x[0]) if x[0].isdigit() else x[0],
        ):
            recent = entries[:last_n]  # keep at most last_n per qubit
            # Chronological order (oldest first) for charting
            chronological = list(reversed(recent))
            values = [e["value"] for e in recent]
            latest = values[0]
            if isinstance(latest, (int, float)) and math.isfinite(latest):
                all_latest.append(float(latest))

            # Columnar timeseries: compact format for charting
            ts_values = [_compact_number(e["value"]) for e in chronological]
            ts_times = [_compact_timestamp(e["start_at"]) for e in chronological]

            qubit_data: dict[str, Any] = {
                "latest": _compact_number(latest),
                "count": len(values),
                "ts": {"v": ts_values, "t": ts_times},
            }
            numeric_values = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
            if len(numeric_values) >= 2:
                qubit_data["min"] = _compact_number(min(numeric_values))
                qubit_data["max"] = _compact_number(max(numeric_values))
                qubit_data["mean"] = _compact_number(stats_mod.mean(numeric_values))
                # Simple trend: compare latest vs oldest
                if numeric_values[0] > numeric_values[-1] * 1.01:
                    qubit_data["trend"] = "up"
                elif numeric_values[0] < numeric_values[-1] * 0.99:
                    qubit_data["trend"] = "down"
                else:
                    qubit_data["trend"] = "stable"
            qubits[qid] = qubit_data

        # Chip-wide statistics
        chip_stats: dict[str, Any] = {
            "count": len(all_latest),
            "mean": stats_mod.mean(all_latest) if all_latest else 0,
            "median": stats_mod.median(all_latest) if all_latest else 0,
            "min": min(all_latest) if all_latest else 0,
            "max": max(all_latest) if all_latest else 0,
        }
        if len(all_latest) >= 2:
            chip_stats["stdev"] = stats_mod.stdev(all_latest)

        result = {
            "chip_id": chip_id,
            "parameter_name": parameter_name,
            "unit": unit,
            "num_qubits": len(qubits),
            "qubits": qubits,
            "statistics": chip_stats,
        }

        # Guard against exceeding the tool result size limit (30K chars).
        # If full timeseries makes it too large, drop timeseries arrays
        # and keep only per-qubit stats so ALL qubits are still represented.
        import json as _json

        _MAX_SAFE_CHARS = 25000  # leave margin for JSON overhead
        result_size = len(_json.dumps(result, default=str, ensure_ascii=False))
        if result_size > _MAX_SAFE_CHARS:
            logger.info(
                "Chip parameter timeseries too large (%d chars, %d qubits x last_n=%d), "
                "dropping timeseries arrays to fit",
                result_size,
                len(qubits),
                last_n,
            )
            for qdata in qubits.values():
                qdata.pop("ts", None)
            result["_note"] = (
                "Timeseries arrays omitted because the full result exceeded size limits. "
                "Per-qubit stats (latest, min, max, mean, trend) and chip-wide statistics "
                "are still included. To get timeseries, call again with a smaller qids list."
            )

        return result

    def load_chip_summary(
        self, chip_id: str, param_names: list[str] | None = None
    ) -> dict[str, Any]:
        """Load summary of all qubits on a chip with computed statistics."""
        from qdash.dbmodel.qubit import QubitDocument

        docs = QubitDocument.find({"chip_id": chip_id}).run()
        if not docs:
            return {"error": f"No qubits found for chip_id={chip_id}"}

        qubits: dict[str, dict[str, Any]] = {}
        numeric_values: dict[str, list[float]] = {}

        for doc in docs:
            data = dict(doc.data)
            if param_names:
                data = {k: v for k, v in data.items() if k in param_names}
            qubits[doc.qid] = sanitize_for_json(data)
            for key, val in data.items():
                raw = val.get("value") if isinstance(val, dict) and "value" in val else val
                if isinstance(raw, (int, float)) and math.isfinite(raw):
                    numeric_values.setdefault(key, []).append(float(raw))

        statistics: dict[str, dict[str, float]] = {}
        for key, values in numeric_values.items():
            if len(values) >= 2:
                statistics[key] = {
                    "mean": stats_mod.mean(values),
                    "median": stats_mod.median(values),
                    "stdev": stats_mod.stdev(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
            elif len(values) == 1:
                statistics[key] = {
                    "mean": values[0],
                    "median": values[0],
                    "stdev": 0.0,
                    "min": values[0],
                    "max": values[0],
                    "count": 1,
                }

        return {
            "chip_id": chip_id,
            "num_qubits": len(qubits),
            "qubits": qubits,
            "statistics": statistics,
        }

    def load_coupling_params_tool(
        self,
        chip_id: str,
        coupling_id: str | None = None,
        qubit_id: str | None = None,
        param_names: list[str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Load coupling parameters by coupling_id or qubit_id."""
        from qdash.dbmodel.coupling import CouplingDocument

        if coupling_id:
            coupling_ids = [coupling_id]
        elif qubit_id:
            from qdash.dbmodel.chip import ChipDocument

            chip = ChipDocument.find_one({"chip_id": chip_id}).run()
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
            doc = CouplingDocument.find_one({"chip_id": chip_id, "qid": cid}).run()
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
        from qdash.dbmodel.execution_history import ExecutionHistoryDocument

        query: dict[str, Any] = {"chip_id": chip_id}
        if status:
            query["status"] = status
        if tags:
            query["tags"] = {"$all": tags}

        docs = (
            ExecutionHistoryDocument.find(query)
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n)
            .run()
        )

        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(
                {
                    "execution_id": doc.execution_id,
                    "name": doc.name,
                    "status": doc.status,
                    "chip_id": doc.chip_id,
                    "tags": doc.tags,
                    "start_at": doc.start_at.isoformat() if doc.start_at else None,
                    "end_at": doc.end_at.isoformat() if doc.end_at else None,
                    "elapsed_time": doc.elapsed_time,
                    "message": doc.message,
                }
            )

        if not results:
            return [{"error": f"No executions found for chip_id={chip_id}"}]
        return results

    def load_compare_qubits(
        self, chip_id: str, qids: list[str], param_names: list[str] | None = None
    ) -> dict[str, Any]:
        """Load and compare parameters across multiple qubits."""
        from qdash.dbmodel.qubit import QubitDocument

        comparison: dict[str, dict[str, Any]] = {}
        for qid in qids:
            doc = QubitDocument.find_one({"chip_id": chip_id, "qid": qid}).run()
            if doc is None:
                comparison[qid] = {"error": f"Qubit {qid} not found"}
                continue
            data = dict(doc.data)
            if param_names:
                data = {k: v for k, v in data.items() if k in param_names}
            comparison[qid] = sanitize_for_json(data)

        return {"chip_id": chip_id, "qubits": comparison}

    def load_chip_topology(self, chip_id: str) -> dict[str, Any]:
        """Load chip topology information."""
        from qdash.dbmodel.chip import ChipDocument

        chip = ChipDocument.find_one({"chip_id": chip_id}).run()
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

        docs = (
            TaskResultHistoryDocument.find(query)
            .sort([("start_at", SortDirection.DESCENDING)])
            .limit(last_n)
            .run()
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
                    "start_at": doc.start_at.isoformat() if doc.start_at else None,
                    "end_at": doc.end_at.isoformat() if doc.end_at else None,
                    "elapsed_time": doc.elapsed_time,
                    "output_parameters": doc.output_parameters or {},
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
        from qdash.dbmodel.calibration_note import CalibrationNoteDocument

        query: dict[str, Any] = {"chip_id": chip_id}
        if execution_id:
            query["execution_id"] = execution_id
        if task_id:
            query["task_id"] = task_id

        docs = (
            CalibrationNoteDocument.find(query)
            .sort([("timestamp", SortDirection.DESCENDING)])
            .limit(last_n)
            .run()
        )

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
        from qdash.dbmodel.chip import ChipDocument

        doc = ChipDocument.find_one({"chip_id": chip_id}).run()
        if doc is None:
            return None
        return str(doc.project_id)

    def _get_provenance_service(self) -> Any:
        """Build a ProvenanceService instance (same pattern as provenance router)."""
        from qdash.api.services.provenance_service import ProvenanceService
        from qdash.repository.provenance import (
            MongoActivityRepository,
            MongoParameterVersionRepository,
            MongoProvenanceRelationRepository,
        )

        return ProvenanceService(
            parameter_version_repo=MongoParameterVersionRepository(),
            provenance_relation_repo=MongoProvenanceRelationRepository(),
            activity_repo=MongoActivityRepository(),
        )

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
        lineage = service.get_lineage(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )

        # Convert to a simplified dict for the LLM
        nodes: list[dict[str, Any]] = []
        for n in lineage.nodes:
            entry: dict[str, Any] = {
                "node_type": n.node_type,
                "node_id": n.node_id,
                "depth": n.depth,
            }
            if n.entity:
                entry["parameter_name"] = n.entity.parameter_name
                entry["qid"] = n.entity.qid
                entry["value"] = n.entity.value
                entry["unit"] = n.entity.unit
                entry["version"] = n.entity.version
                entry["task_name"] = n.entity.task_name
                entry["execution_id"] = n.entity.execution_id
                if n.entity.valid_from:
                    entry["valid_from"] = n.entity.valid_from.isoformat()
            if n.activity:
                entry["task_name"] = n.activity.task_name
                entry["task_type"] = n.activity.task_type
                entry["qid"] = n.activity.qid
                entry["execution_id"] = n.activity.execution_id
                entry["status"] = n.activity.status
            if n.latest_version is not None:
                entry["latest_version"] = n.latest_version
            nodes.append(entry)

        edges: list[dict[str, str]] = []
        for e in lineage.edges:
            edges.append(
                {
                    "relation_type": e.relation_type,
                    "source": e.source_id,
                    "target": e.target_id,
                }
            )

        return {
            "origin": lineage.origin.node_id,
            "num_nodes": len(nodes),
            "num_edges": len(edges),
            "max_depth": lineage.max_depth,
            "nodes": nodes,
            "edges": edges,
        }

    def load_parameter_lineage(
        self, parameter_name: str, qid: str, chip_id: str, last_n: int = 10
    ) -> list[dict[str, Any]]:
        """Load version history for a specific parameter."""
        from qdash.dbmodel.provenance import ParameterVersionDocument

        docs = (
            ParameterVersionDocument.find(
                {"parameter_name": parameter_name, "qid": qid, "chip_id": chip_id}
            )
            .sort([("version", SortDirection.DESCENDING)])
            .limit(last_n)
            .run()
        )

        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(
                {
                    "version": doc.version,
                    "value": doc.value,
                    "unit": doc.unit,
                    "error": doc.error,
                    "execution_id": doc.execution_id,
                    "task_id": doc.task_id,
                    "task_name": doc.task_name,
                    "valid_from": doc.valid_from.isoformat() if doc.valid_from else None,
                    "valid_until": doc.valid_until.isoformat() if doc.valid_until else None,
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
        from datetime import timedelta

        from qdash.api.lib.metrics_chart import (
            build_chip_geometry,
            chip_geometry_from_topology,
            create_qubit_heatmap,
        )
        from qdash.api.lib.metrics_config import get_qubit_metric_metadata, load_metrics_config
        from qdash.common.topology_config import load_topology
        from qdash.dbmodel.chip import ChipDocument
        from qdash.repository.task_result_history import MongoTaskResultHistoryRepository

        # Validate metric name
        meta = get_qubit_metric_metadata(metric_name)
        if meta is None:
            config = load_metrics_config()
            available = sorted(config.qubit_metrics.keys())
            return {
                "error": (
                    f"Unknown qubit metric '{metric_name}'. "
                    f"Available metrics: {', '.join(available)}"
                )
            }

        # Resolve chip
        chip = ChipDocument.find_one({"chip_id": chip_id}).run()
        if chip is None:
            return {"error": f"Chip '{chip_id}' not found"}
        project_id = str(chip.project_id)

        # Build geometry
        if chip.topology_id:
            try:
                topology = load_topology(chip.topology_id)
                geometry = chip_geometry_from_topology(topology)
            except (FileNotFoundError, ValueError, KeyError) as e:
                logger.warning("Failed to load topology '%s': %s", chip.topology_id, e)
                n = chip.size or 0
                geometry = build_chip_geometry(n, int(math.sqrt(n)) if n else 1)
        else:
            n = chip.size or 0
            geometry = build_chip_geometry(n, int(math.sqrt(n)) if n else 1)

        # Cutoff time
        cutoff_time = None
        if within_hours:
            from qdash.common.datetime_utils import now

            cutoff_time = now() - timedelta(hours=within_hours)

        # Aggregate metrics
        repo = MongoTaskResultHistoryRepository()
        valid_keys = {metric_name}

        try:
            if selection_mode == "best":
                eval_mode = meta.evaluation.mode
                if eval_mode == "maximize" or eval_mode == "minimize":
                    agg = repo.aggregate_best_metrics(
                        chip_id=chip_id,
                        project_id=project_id,
                        entity_type="qubit",
                        metric_modes={metric_name: eval_mode},
                        cutoff_time=cutoff_time,
                    )
                else:
                    agg = repo.aggregate_latest_metrics(
                        chip_id=chip_id,
                        project_id=project_id,
                        entity_type="qubit",
                        metric_keys=valid_keys,
                        cutoff_time=cutoff_time,
                    )
            elif selection_mode == "average":
                agg = repo.aggregate_average_metrics(
                    chip_id=chip_id,
                    project_id=project_id,
                    entity_type="qubit",
                    metric_keys=valid_keys,
                    cutoff_time=cutoff_time,
                )
            else:
                agg = repo.aggregate_latest_metrics(
                    chip_id=chip_id,
                    project_id=project_id,
                    entity_type="qubit",
                    metric_keys=valid_keys,
                    cutoff_time=cutoff_time,
                )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Metrics aggregation failed for %s/%s: %s", chip_id, metric_name, e)
            return {"error": f"Failed to aggregate metrics: {e}"}

        # Build MetricValue-like objects for the chart helper
        from qdash.api.schemas.metrics import MetricValue

        metric_data: dict[str, MetricValue] = {}
        for entity_id, result in agg.get(metric_name, {}).items():
            metric_data[entity_id] = MetricValue(
                value=result["value"],
                task_id=result.get("task_id"),
                execution_id=result["execution_id"],
                stddev=result.get("stddev"),
            )

        if not metric_data:
            return {"error": f"No data found for metric '{metric_name}' on chip '{chip_id}'"}

        fig = create_qubit_heatmap(
            metric_data=metric_data,
            geometry=geometry,
            metric_scale=meta.scale,
            metric_title=meta.title,
            metric_unit=meta.unit,
            compact=True,
        )

        # Compute basic statistics
        raw_values = [mv.value * meta.scale for mv in metric_data.values() if mv.value is not None]
        statistics: dict[str, Any] = {}
        if raw_values:
            import numpy as np

            statistics = {
                "count": len(raw_values),
                "total_qubits": geometry.n_qubits,
                "coverage": f"{len(raw_values) / geometry.n_qubits * 100:.1f}%",
                "median": float(np.median(raw_values)),
                "mean": float(np.mean(raw_values)),
                "min": float(np.min(raw_values)),
                "max": float(np.max(raw_values)),
                "unit": meta.unit,
            }

        fig_dict = fig.to_dict()
        return {
            "chart": {"data": fig_dict["data"], "layout": fig_dict["layout"]},
            "statistics": statistics,
        }

    def load_available_parameters(
        self,
        chip_id: str,
        qid: str | None = None,
    ) -> dict[str, Any]:
        """List distinct output parameter names recorded for a chip."""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        query: dict[str, Any] = {"chip_id": chip_id, "status": "completed"}
        if qid:
            query["qid"] = qid

        # Use MongoDB distinct on the output_parameter_names array field
        collection = TaskResultHistoryDocument.get_motor_collection()
        try:
            names = collection.distinct("output_parameter_names", query)
        except (AttributeError, TypeError) as e:
            # Fallback: manual aggregation when distinct() is unavailable
            logger.warning("distinct() failed for output_parameter_names: %s", e)
            docs = TaskResultHistoryDocument.find(query).limit(FALLBACK_QUERY_LIMIT).run()
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
        from qdash.api.lib.copilot_analysis import (
            AnalysisContextResult,
            TaskAnalysisContext,
        )
        from qdash.datamodel.task_knowledge import get_task_knowledge

        # Resolve task knowledge
        knowledge = get_task_knowledge(task_name)
        knowledge_prompt = knowledge.to_prompt() if knowledge else f"Task: {task_name}"

        # Load qubit parameters
        qubit_params = self.load_qubit_params(chip_id, qid)

        # Load task result parameters
        task_result = self.load_task_result(task_id)
        input_params = task_result.get("input_parameters", {}) if task_result else {}
        output_params = task_result.get("output_parameters", {}) if task_result else {}
        run_params = task_result.get("run_parameters", {}) if task_result else {}

        # Load dynamic context from TaskKnowledge.related_context
        history_results: list[dict[str, Any]] = []
        neighbor_qubit_params: dict[str, dict[str, Any]] = {}
        coupling_params: dict[str, dict[str, Any]] = {}
        if knowledge and knowledge.related_context:
            for rc in knowledge.related_context:
                if rc.type == "history":
                    history_results = self.load_task_history(task_name, chip_id, qid, rc.last_n)
                elif rc.type == "neighbor_qubits":
                    neighbor_qubit_params = self.load_neighbor_qubit_params(chip_id, qid, rc.params)
                elif rc.type == "coupling":
                    coupling_params = self.load_coupling_params(chip_id, qid, rc.params)

        # Auto-load experiment figure if not provided and multimodal is enabled
        expected_images: list[tuple[str, str]] = []
        figure_paths: list[str] = task_result.get("figure_path", []) if task_result else []
        if config.analysis.multimodal:
            if not image_base64 and task_result:
                image_base64 = self.load_figure_as_base64(figure_paths)
            expected_images = self.collect_expected_images(knowledge)

        context = TaskAnalysisContext(
            task_knowledge_prompt=knowledge_prompt,
            chip_id=chip_id,
            qid=qid,
            qubit_params=qubit_params,
            input_parameters=input_params,
            output_parameters=output_params,
            run_parameters=run_params,
            history_results=history_results,
            neighbor_qubit_params=neighbor_qubit_params,
            coupling_params=coupling_params,
        )

        return AnalysisContextResult(
            context=context,
            image_base64=image_base64,
            expected_images=expected_images,
            figure_paths=figure_paths,
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
        """Build the tool executor mapping for LLM function calling."""
        from qdash.api.lib.copilot_sandbox import execute_python_analysis

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
            "execute_python_analysis": lambda args: execute_python_analysis(
                args["code"], args.get("context_data")
            ),
            "get_chip_summary": lambda args: self.load_chip_summary(
                args["chip_id"], args.get("param_names")
            ),
            "get_coupling_params": lambda args: self.load_coupling_params_tool(
                args["chip_id"],
                args.get("coupling_id"),
                args.get("qubit_id"),
                args.get("param_names"),
            ),
            "get_execution_history": lambda args: self.load_execution_history(
                args["chip_id"], args.get("status"), args.get("tags"), args.get("last_n", 10)
            ),
            "compare_qubits": lambda args: self.load_compare_qubits(
                args["chip_id"], args["qids"], args.get("param_names")
            ),
            "get_chip_topology": lambda args: self.load_chip_topology(args["chip_id"]),
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
