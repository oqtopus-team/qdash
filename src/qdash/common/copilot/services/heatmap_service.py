"""Chip-heatmap loading helpers for Copilot data access."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Protocol, cast

logger = logging.getLogger(__name__)


@dataclass
class MetricValue:
    """Minimal metric payload for shared chart helpers."""

    value: float | None = None
    task_id: str | None = None
    execution_id: str | None = None
    stddev: float | None = None


@dataclass(frozen=True)
class HeatmapContext:
    """Resolved inputs needed to build a chip heatmap response."""

    chip: Any
    project_id: str
    meta: Any
    geometry: Any
    cutoff_time: Any


class TaskResultHistoryRepositoryProtocol(Protocol):
    def aggregate_best_metrics(
        self,
        *,
        chip_id: str,
        project_id: str,
        entity_type: str,
        metric_modes: dict[str, str],
        cutoff_time: Any = None,
    ) -> dict[str, dict[str, dict[str, Any]]]: ...

    def aggregate_latest_metrics(
        self,
        *,
        chip_id: str,
        project_id: str,
        entity_type: str,
        metric_keys: set[str],
        cutoff_time: Any = None,
    ) -> dict[str, dict[str, dict[str, Any]]]: ...

    def aggregate_average_metrics(
        self,
        *,
        chip_id: str,
        project_id: str,
        entity_type: str,
        metric_keys: set[str],
        cutoff_time: Any = None,
    ) -> dict[str, dict[str, dict[str, Any]]]: ...


class ChipHeatmapLoader:
    """Generate chip-wide heatmap payloads for Copilot tools."""

    def __init__(
        self,
        *,
        data_access: Any,
        compact_number: Any,
    ) -> None:
        self._data_access = data_access
        self._compact_number = compact_number

    def load_chip_heatmap(
        self,
        *,
        chip_id: str,
        metric_name: str,
        selection_mode: str = "latest",
        within_hours: int | None = None,
    ) -> dict[str, Any]:
        """Generate a chip-wide heatmap for a qubit metric."""
        from datetime import timedelta

        from qdash.common.config.metrics import get_qubit_metric_metadata, load_metrics_config
        from qdash.common.config.topology import load_topology
        from qdash.common.visualization.metrics_chart import (
            build_chip_geometry,
            chip_geometry_from_topology,
            create_qubit_heatmap,
        )

        meta = get_qubit_metric_metadata(metric_name)
        if meta is None:
            return self._unknown_heatmap_metric_error(metric_name, load_metrics_config)

        chip = self._data_access.load_chip(chip_id)
        if chip is None:
            return {"error": f"Chip '{chip_id}' not found"}

        context = HeatmapContext(
            chip=chip,
            project_id=str(chip.project_id),
            meta=meta,
            geometry=self._build_chip_heatmap_geometry(
                chip=chip,
                load_topology=load_topology,
                build_chip_geometry=build_chip_geometry,
                chip_geometry_from_topology=chip_geometry_from_topology,
            ),
            cutoff_time=self._build_heatmap_cutoff_time(within_hours, timedelta),
        )
        metric_data_or_error = self._load_chip_heatmap_metric_data(
            chip_id=chip_id,
            metric_name=metric_name,
            selection_mode=selection_mode,
            context=context,
        )
        if "error" in metric_data_or_error:
            return metric_data_or_error
        metric_data = cast("dict[str, MetricValue]", metric_data_or_error)
        if not metric_data:
            return {"error": f"No data found for metric '{metric_name}' on chip '{chip_id}'"}

        fig = create_qubit_heatmap(
            metric_data=metric_data,
            geometry=context.geometry,
            metric_scale=context.meta.scale,
            metric_title=context.meta.title,
            metric_unit=context.meta.unit,
            compact=True,
        )
        statistics = self._build_chip_heatmap_statistics(
            metric_data=metric_data,
            geometry=context.geometry,
            meta=context.meta,
        )
        fig_dict = fig.to_dict()
        return {
            "chart": {"data": fig_dict["data"], "layout": fig_dict["layout"]},
            "statistics": statistics,
        }

    @staticmethod
    def _unknown_heatmap_metric_error(metric_name: str, load_metrics_config: Any) -> dict[str, str]:
        config = load_metrics_config()
        available = sorted(config.qubit_metrics.keys())
        return {
            "error": (
                f"Unknown qubit metric '{metric_name}'. Available metrics: {', '.join(available)}"
            )
        }

    def _build_chip_heatmap_geometry(
        self,
        *,
        chip: Any,
        load_topology: Any,
        build_chip_geometry: Any,
        chip_geometry_from_topology: Any,
    ) -> Any:
        if chip.topology_id:
            try:
                topology = load_topology(chip.topology_id)
                return chip_geometry_from_topology(topology)
            except (FileNotFoundError, ValueError, KeyError) as exc:
                logger.warning("Failed to load topology '%s': %s", chip.topology_id, exc)
        return self._build_fallback_chip_geometry(chip, build_chip_geometry)

    @staticmethod
    def _build_fallback_chip_geometry(chip: Any, build_chip_geometry: Any) -> Any:
        n_qubits = chip.size or 0
        return build_chip_geometry(n_qubits, int(math.sqrt(n_qubits)) if n_qubits else 1)

    @staticmethod
    def _build_heatmap_cutoff_time(within_hours: int | None, timedelta_type: Any) -> Any:
        if not within_hours:
            return None
        from qdash.common.utils.datetime import now

        return now() - timedelta_type(hours=within_hours)

    def _load_chip_heatmap_metric_data(
        self,
        *,
        chip_id: str,
        metric_name: str,
        selection_mode: str,
        context: HeatmapContext,
    ) -> dict[str, MetricValue] | dict[str, str]:
        repo = self._data_access.create_task_result_history_repository()
        try:
            aggregation = self._aggregate_chip_heatmap_metrics(
                repo=repo,
                chip_id=chip_id,
                metric_name=metric_name,
                selection_mode=selection_mode,
                context=context,
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Metrics aggregation failed for %s/%s: %s", chip_id, metric_name, exc)
            return {"error": f"Failed to aggregate metrics: {exc}"}
        return self._normalize_chip_heatmap_metric_data(aggregation, metric_name)

    @staticmethod
    def _aggregate_chip_heatmap_metrics(
        *,
        repo: TaskResultHistoryRepositoryProtocol,
        chip_id: str,
        metric_name: str,
        selection_mode: str,
        context: HeatmapContext,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        metric_keys = {metric_name}
        if selection_mode == "best":
            eval_mode = context.meta.evaluation.mode
            if eval_mode in {"maximize", "minimize"}:
                return repo.aggregate_best_metrics(
                    chip_id=chip_id,
                    project_id=context.project_id,
                    entity_type="qubit",
                    metric_modes={metric_name: eval_mode},
                    cutoff_time=context.cutoff_time,
                )
            return repo.aggregate_latest_metrics(
                chip_id=chip_id,
                project_id=context.project_id,
                entity_type="qubit",
                metric_keys=metric_keys,
                cutoff_time=context.cutoff_time,
            )
        if selection_mode == "average":
            return repo.aggregate_average_metrics(
                chip_id=chip_id,
                project_id=context.project_id,
                entity_type="qubit",
                metric_keys=metric_keys,
                cutoff_time=context.cutoff_time,
            )
        return repo.aggregate_latest_metrics(
            chip_id=chip_id,
            project_id=context.project_id,
            entity_type="qubit",
            metric_keys=metric_keys,
            cutoff_time=context.cutoff_time,
        )

    @staticmethod
    def _normalize_chip_heatmap_metric_data(
        aggregation: dict[str, dict[str, dict[str, Any]]],
        metric_name: str,
    ) -> dict[str, MetricValue]:
        metric_data: dict[str, MetricValue] = {}
        for entity_id, result in aggregation.get(metric_name, {}).items():
            metric_data[entity_id] = MetricValue(
                value=result["value"],
                task_id=result.get("task_id"),
                execution_id=result["execution_id"],
                stddev=result.get("stddev"),
            )
        return metric_data

    def _build_chip_heatmap_statistics(
        self,
        *,
        metric_data: dict[str, MetricValue],
        geometry: Any,
        meta: Any,
    ) -> dict[str, Any]:
        raw_values = [mv.value * meta.scale for mv in metric_data.values() if mv.value is not None]
        if not raw_values:
            return {}

        import numpy as np

        return {
            "count": len(raw_values),
            "total_qubits": geometry.n_qubits,
            "coverage": f"{len(raw_values) / geometry.n_qubits * 100:.1f}%",
            "median": float(np.median(raw_values)),
            "mean": float(np.mean(raw_values)),
            "min": float(np.min(raw_values)),
            "max": float(np.max(raw_values)),
            "unit": meta.unit,
        }
