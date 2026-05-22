"""Provenance service for querying calibration data lineage.

This module provides the ProvenanceService class that handles business logic
for provenance queries, delegating to repositories for data access.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from qdash.api.schemas.provenance import (
    ActivityResponse,
    DegradationTrendResponse,
    DegradationTrendsResponse,
    ExecutionComparisonResponse,
    ExecutionIdResponse,
    ImpactResponse,
    LineageEdgeResponse,
    LineageNodeResponse,
    LineageResponse,
    ParameterChangeResponse,
    ParameterDiffResponse,
    ParameterHistoryResponse,
    ParameterVersionResponse,
    ProvenanceStatsResponse,
    RecalibrationRecommendationResponse,
    RecentChangesResponse,
    RecentExecutionsResponse,
    RecommendedTaskResponse,
)
from qdash.common.config.metrics import MetricMetadata, load_metrics_config

if TYPE_CHECKING:
    from qdash.repository.provenance import (
        MongoActivityRepository,
        MongoParameterVersionRepository,
        MongoProvenanceRelationRepository,
    )

logger = logging.getLogger(__name__)


_VERSIONS_BUFFER = 5  # Extra versions to fetch beyond min_streak


@dataclass(frozen=True)
class _DegradationTrendConfig:
    """Inputs needed to evaluate degradation trends across parameter versions."""

    target_params: list[str]
    eval_modes: dict[str, str]
    all_metrics: dict[str, MetricMetadata]


@dataclass
class _RecommendationTaskInfo:
    """Accumulated impact-graph state for one recommended recalibration task."""

    qids: set[str]
    parameters: set[str]
    min_depth: float
    example: tuple[str, str, int] | None = None


@dataclass(frozen=True)
class _RecalibrationRecommendationContext:
    """Shared context derived from the impact graph for recommendation building."""

    source_param_name: str
    source_qid: str
    task_info: dict[str, _RecommendationTaskInfo]
    affected_entity_count: int
    max_depth_reached: int


class ProvenanceService:
    """Service for provenance queries.

    This service provides methods for querying calibration data lineage,
    including ancestor/descendant traversal, execution comparison, and
    parameter history.

    Attributes
    ----------
    parameter_version_repo : MongoParameterVersionRepository
        Repository for parameter versions
    provenance_relation_repo : MongoProvenanceRelationRepository
        Repository for provenance relations
    activity_repo : MongoActivityRepository
        Repository for activities

    """

    def __init__(
        self,
        parameter_version_repo: MongoParameterVersionRepository,
        provenance_relation_repo: MongoProvenanceRelationRepository,
        activity_repo: MongoActivityRepository,
    ) -> None:
        """Initialize ProvenanceService.

        Parameters
        ----------
        parameter_version_repo : MongoParameterVersionRepository
            Repository for parameter versions
        provenance_relation_repo : MongoProvenanceRelationRepository
            Repository for provenance relations
        activity_repo : MongoActivityRepository
            Repository for activities

        """
        self.parameter_version_repo = parameter_version_repo
        self.provenance_relation_repo = provenance_relation_repo
        self.activity_repo = activity_repo

    def get_lineage(
        self,
        project_id: str,
        entity_id: str,
        max_depth: int = 10,
    ) -> LineageResponse:
        """Get the lineage (ancestors) of a parameter version.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity ID to trace lineage from
        max_depth : int
            Maximum depth to traverse

        Returns
        -------
        LineageResponse
            Lineage graph with nodes and edges

        """
        # Use provenance relation repo for graph traversal
        lineage_data = self.provenance_relation_repo.get_lineage(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )
        nodes, edges = self._build_graph_responses(lineage_data, origin_id=entity_id, reverse=False)

        # Enrich entity nodes with latest version info (staleness check)
        self._enrich_nodes_with_latest_version(project_id, nodes)

        return LineageResponse(
            origin=self._find_graph_origin(nodes, entity_id),
            nodes=nodes,
            edges=edges,
            max_depth=max_depth,
        )

    def get_impact(
        self,
        project_id: str,
        entity_id: str,
        max_depth: int = 10,
    ) -> ImpactResponse:
        """Get the impact (descendants) of a parameter version.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity ID to trace impact from
        max_depth : int
            Maximum depth to traverse

        Returns
        -------
        ImpactResponse
            Impact graph with affected nodes and edges

        """
        # Use provenance relation repo for graph traversal
        impact_data = self.provenance_relation_repo.get_impact(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )
        nodes, edges = self._build_graph_responses(impact_data, origin_id=entity_id, reverse=True)

        return ImpactResponse(
            origin=self._find_graph_origin(nodes, entity_id),
            nodes=nodes,
            edges=edges,
            max_depth=max_depth,
        )

    def _build_graph_responses(
        self,
        graph_data: Any,
        *,
        origin_id: str,
        reverse: bool,
    ) -> tuple[list[LineageNodeResponse], list[LineageEdgeResponse]]:
        """Convert raw graph data into schema nodes and edges with computed depths."""
        nodes = [self._build_graph_node(node_item) for node_item in graph_data.get("nodes", [])]
        edges = self._build_lineage_edges(graph_data.get("edges", []))
        depths = self._compute_graph_depths(origin_id=origin_id, edges=edges, reverse=reverse)
        for node in nodes:
            node.depth = depths.get(node.node_id, 0)
        return nodes, edges

    def _build_graph_node(self, node_item: Any) -> LineageNodeResponse:
        """Convert one raw graph node into the shared response schema."""
        node_dict = dict(node_item)
        node_type = str(node_dict.get("type", "entity"))
        return LineageNodeResponse(
            node_type=node_type,
            node_id=str(node_dict.get("id", "")),
            depth=0,
            entity=self._build_version_from_metadata(node_dict) if node_type == "entity" else None,
            activity=self._build_activity_from_metadata(node_dict)
            if node_type == "activity"
            else None,
        )

    @staticmethod
    def _find_graph_origin(
        nodes: list[LineageNodeResponse],
        entity_id: str,
    ) -> LineageNodeResponse:
        """Return the origin node if present, or a placeholder entity node otherwise."""
        return next(
            (node for node in nodes if node.node_id == entity_id),
            LineageNodeResponse(node_type="entity", node_id=entity_id, depth=0),
        )

    @staticmethod
    def _compute_graph_depths(
        *,
        origin_id: str,
        edges: list[LineageEdgeResponse],
        reverse: bool,
    ) -> dict[str, int]:
        """Compute shortest-path depths from origin using graph edges.

        Notes
        -----
        - For lineage graphs, edges are traversed from source_id -> target_id.
        - For impact graphs, downstream traversal follows the reverse direction
          (target_id -> source_id) of recorded PROV edges.
        """
        adjacency: dict[str, list[str]] = defaultdict(list)
        for e in edges:
            if reverse:
                adjacency[e.target_id].append(e.source_id)
            else:
                adjacency[e.source_id].append(e.target_id)

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

    def _enrich_nodes_with_latest_version(
        self,
        project_id: str,
        nodes: list[LineageNodeResponse],
    ) -> None:
        """Annotate entity nodes whose version is behind the current version.

        For each entity node, if a newer version exists, sets
        ``node.latest_version`` to the current version number.

        Parameters
        ----------
        project_id : str
            Project identifier
        nodes : list[LineageNodeResponse]
            Nodes to enrich (modified in place)

        """
        # Collect (parameter_name, qid) pairs for entity nodes
        entity_nodes = [n for n in nodes if n.node_type == "entity" and n.entity]
        if not entity_nodes:
            return

        keys: set[tuple[str, str]] = set()
        for node in entity_nodes:
            assert node.entity is not None
            keys.add((node.entity.parameter_name, node.entity.qid))

        if not keys:
            return

        # Bulk-fetch current versions
        current_docs = self.parameter_version_repo.get_current_many(
            project_id,
            keys=sorted(keys),
        )

        # Build lookup: (parameter_name, qid) -> current version number
        current_version_map: dict[tuple[str, str], int] = {}
        for doc in current_docs:
            current_version_map[(doc.parameter_name, getattr(doc, "qid", ""))] = getattr(
                doc, "version", 1
            )

        # Annotate nodes where a newer version exists
        for node in entity_nodes:
            assert node.entity is not None
            key = (node.entity.parameter_name, node.entity.qid)
            current_ver = current_version_map.get(key)
            if current_ver is not None and current_ver > node.entity.version:
                node.latest_version = current_ver

    def compare_executions(
        self,
        project_id: str,
        execution_id_before: str,
        execution_id_after: str,
    ) -> ExecutionComparisonResponse:
        """Compare parameter values between two executions.

        Parameters
        ----------
        project_id : str
            Project identifier
        execution_id_before : str
            First execution ID
        execution_id_after : str
            Second execution ID

        Returns
        -------
        ExecutionComparisonResponse
            Comparison of parameter values

        """
        # Use provenance relation repo for comparison
        diffs = self.provenance_relation_repo.compare_executions(
            project_id=project_id,
            execution_id_1=execution_id_before,
            execution_id_2=execution_id_after,
        )

        added, removed, changed = self._partition_execution_diffs(diffs)

        return ExecutionComparisonResponse(
            execution_id_before=execution_id_before,
            execution_id_after=execution_id_after,
            added_parameters=added,
            removed_parameters=removed,
            changed_parameters=changed,
            unchanged_count=0,
        )

    def _partition_execution_diffs(
        self,
        diffs: list[Any],
    ) -> tuple[
        list[ParameterDiffResponse],
        list[ParameterDiffResponse],
        list[ParameterDiffResponse],
    ]:
        """Split raw execution diffs into added, removed, and changed response lists."""
        added: list[ParameterDiffResponse] = []
        removed: list[ParameterDiffResponse] = []
        changed: list[ParameterDiffResponse] = []

        for diff in diffs:
            param_diff = self._build_execution_diff(diff)
            change_type = diff.get("change_type", "")
            if change_type == "added":
                added.append(param_diff)
            elif change_type == "removed":
                removed.append(param_diff)
            elif change_type == "changed":
                changed.append(param_diff)

        return added, removed, changed

    def _build_execution_diff(self, diff: Any) -> ParameterDiffResponse:
        """Convert one raw repository diff into the API response schema."""
        before_data = diff.get("before")
        after_data = diff.get("after")
        value_before = before_data.get("value") if before_data else None
        value_after = after_data.get("value") if after_data else None
        delta, delta_percent = self._calculate_execution_diff_delta(
            change_type=diff.get("change_type", ""),
            value_before=value_before,
            value_after=value_after,
        )
        return ParameterDiffResponse(
            parameter_name=diff.get("parameter_name", ""),
            qid=diff.get("qid", ""),
            value_before=value_before,
            value_after=value_after,
            delta=delta,
            delta_percent=delta_percent,
        )

    @staticmethod
    def _calculate_execution_diff_delta(
        *,
        change_type: str,
        value_before: Any,
        value_after: Any,
    ) -> tuple[float | None, float | None]:
        """Calculate numeric deltas for changed parameters only."""
        if (
            change_type != "changed"
            or not isinstance(value_before, (int, float))
            or not isinstance(value_after, (int, float))
        ):
            return None, None
        delta = float(value_after) - float(value_before)
        if value_before == 0:
            return delta, None
        return delta, (delta / float(value_before)) * 100

    def get_parameter_history(
        self,
        project_id: str,
        parameter_name: str,
        qid: str,
        limit: int = 50,
    ) -> ParameterHistoryResponse:
        """Get version history for a parameter.

        Parameters
        ----------
        project_id : str
            Project identifier
        parameter_name : str
            Name of the parameter
        qid : str
            Qubit or coupling identifier
        limit : int
            Maximum number of versions to return

        Returns
        -------
        ParameterHistoryResponse
            List of parameter versions

        """
        versions = self.parameter_version_repo.get_version_history(
            project_id=project_id,
            parameter_name=parameter_name,
            qid=qid,
            limit=limit,
        )

        version_responses = [self._build_version_response(v) for v in versions]

        return ParameterHistoryResponse(
            parameter_name=parameter_name,
            qid=qid,
            versions=version_responses,
            total_versions=len(version_responses),
        )

    def get_stats(self, project_id: str) -> ProvenanceStatsResponse:
        """Get provenance statistics for a project.

        Parameters
        ----------
        project_id : str
            Project identifier

        Returns
        -------
        ProvenanceStatsResponse
            Provenance statistics

        """
        try:
            # Get counts from repositories
            total_entities = self.parameter_version_repo.count(project_id)
            total_activities = self.activity_repo.count(project_id)
            total_relations = self.provenance_relation_repo.count(project_id)
            relation_counts = self.provenance_relation_repo.count_by_type(project_id)

            # Get recent parameter versions (100 to ensure we get multiple unique execution_ids)
            recent_docs = self.parameter_version_repo.get_recent(project_id, limit=100)
            recent_entities = [self._build_version_response(doc) for doc in recent_docs]
        except Exception as e:
            logger.warning(f"Failed to get provenance stats: {e}")
            # Return empty stats if queries fail (e.g., collections don't exist)
            return ProvenanceStatsResponse(
                total_entities=0,
                total_activities=0,
                total_relations=0,
                relation_counts={},
                recent_entities=[],
            )

        return ProvenanceStatsResponse(
            total_entities=total_entities,
            total_activities=total_activities,
            total_relations=total_relations,
            relation_counts=relation_counts,
            recent_entities=recent_entities,
        )

    def get_recent_executions(
        self,
        project_id: str,
        limit: int = 20,
    ) -> RecentExecutionsResponse:
        """Get recent unique execution IDs.

        Uses MongoDB aggregation to efficiently get distinct execution IDs
        without fetching all parameter versions.

        Parameters
        ----------
        project_id : str
            Project identifier
        limit : int
            Maximum number of execution IDs to return

        Returns
        -------
        RecentExecutionsResponse
            List of recent execution IDs

        """
        try:
            execution_data = self.parameter_version_repo.get_recent_execution_ids(
                project_id, limit=limit
            )
            executions = [
                ExecutionIdResponse(
                    execution_id=item.get("execution_id", ""),
                    valid_from=item.get("valid_from"),
                )
                for item in execution_data
                if item.get("execution_id")
            ]
        except Exception as e:
            logger.warning(f"Failed to get recent executions: {e}")
            executions = []

        return RecentExecutionsResponse(executions=executions)

    def get_recent_changes(
        self,
        project_id: str,
        limit: int = 20,
        within_hours: int = 24,
        parameter_names: list[str] | None = None,
    ) -> RecentChangesResponse:
        """Get recent parameter changes with delta from previous versions.

        Parameters
        ----------
        project_id : str
            Project identifier
        limit : int
            Maximum number of changes to return
        within_hours : int
            Time window in hours (default: 24)
        parameter_names : list[str] | None
            Filter by parameter names (e.g., from metrics.yaml config)

        Returns
        -------
        RecentChangesResponse
            Recent changes with delta information

        """
        try:
            recent_docs = self._load_recent_change_candidates(
                project_id=project_id,
                limit=limit,
                parameter_names=parameter_names,
            )
            changes = self._build_recent_changes(
                project_id=project_id,
                recent_docs=recent_docs,
                limit=limit,
                parameter_names=parameter_names,
            )

            return RecentChangesResponse(
                changes=changes,
                total_count=len(changes),
            )
        except Exception as e:
            logger.warning(f"Failed to get recent changes: {e}")
            return RecentChangesResponse(changes=[], total_count=0)

    def _load_recent_change_candidates(
        self,
        *,
        project_id: str,
        limit: int,
        parameter_names: list[str] | None,
    ) -> list[Any]:
        """Load enough recent versions to satisfy filtering and version checks."""
        fetch_limit = limit * 5 if parameter_names else limit * 2
        return self.parameter_version_repo.get_recent(project_id, limit=fetch_limit)

    def _build_recent_changes(
        self,
        *,
        project_id: str,
        recent_docs: list[Any],
        limit: int,
        parameter_names: list[str] | None,
    ) -> list[ParameterChangeResponse]:
        """Convert recent version documents into change responses."""
        changes: list[ParameterChangeResponse] = []
        for doc in recent_docs:
            if len(changes) >= limit:
                break
            if not self._is_recent_change_candidate(doc, parameter_names):
                continue
            change = self._build_recent_change(project_id=project_id, doc=doc)
            if change is not None:
                changes.append(change)
        return changes

    @staticmethod
    def _is_recent_change_candidate(doc: Any, parameter_names: list[str] | None) -> bool:
        """Return whether a recent version doc should be diffed against its predecessor."""
        if parameter_names and getattr(doc, "parameter_name", "") not in parameter_names:
            return False
        return getattr(doc, "version", 1) > 1

    def _build_recent_change(
        self,
        *,
        project_id: str,
        doc: Any,
    ) -> ParameterChangeResponse | None:
        """Build one recent-change response from a current and previous version pair."""
        from qdash.common.utils.datetime import ensure_timezone

        current_version = getattr(doc, "version", 1)
        if current_version <= 1:
            return None

        previous = self.parameter_version_repo.get_version(
            project_id=project_id,
            parameter_name=doc.parameter_name,
            qid=doc.qid,
            version=current_version - 1,
        )
        current_value = getattr(doc, "value", None)
        previous_value = getattr(previous, "value", None) if previous else None
        current_error = float(getattr(doc, "error", 0.0) or 0.0)
        previous_error = float(getattr(previous, "error", 0.0) or 0.0) if previous else None
        delta, delta_percent = self._calculate_recent_change_delta(current_value, previous_value)

        return ParameterChangeResponse(
            entity_id=doc.entity_id,
            parameter_name=doc.parameter_name,
            qid=doc.qid,
            value=self._sanitize_value(current_value),
            previous_value=self._sanitize_value(previous_value)
            if previous_value is not None
            else None,
            unit=getattr(doc, "unit", ""),
            delta=delta,
            delta_percent=delta_percent,
            version=current_version,
            valid_from=ensure_timezone(getattr(doc, "valid_from", None)),
            task_name=getattr(doc, "task_name", ""),
            execution_id=getattr(doc, "execution_id", ""),
            error=current_error,
            previous_error=previous_error,
        )

    @staticmethod
    def _calculate_recent_change_delta(
        current_value: Any,
        previous_value: Any,
    ) -> tuple[float | None, float | None]:
        """Calculate absolute and percent delta between numeric version values."""
        if not isinstance(current_value, (int, float)) or not isinstance(
            previous_value, (int, float)
        ):
            return None, None
        delta = float(current_value) - float(previous_value)
        if previous_value == 0:
            return delta, None
        return delta, (delta / float(previous_value)) * 100

    def get_degradation_trends(
        self,
        project_id: str,
        *,
        min_streak: int = 3,
        limit: int = 50,
        parameter_names: list[str] | None = None,
    ) -> DegradationTrendsResponse:
        """Detect parameters with consecutive degradation across versions.

        For each (parameter_name, qid), checks whether the value has been
        consistently worsening (based on evaluation mode) over multiple
        consecutive versions.

        Parameters
        ----------
        project_id : str
            Project identifier
        min_streak : int
            Minimum consecutive worsening steps to report (default: 3)
        limit : int
            Maximum number of trends to return
        parameter_names : list[str] | None
            Filter by parameter names

        Returns
        -------
        DegradationTrendsResponse
            Detected degradation trends sorted by severity

        """
        try:
            trend_config = self._build_degradation_trend_config(parameter_names)
            if not trend_config.target_params:
                return DegradationTrendsResponse(trends=[], total_count=0)

            bulk_data = self.parameter_version_repo.get_recent_versions_bulk(
                project_id,
                parameter_names=trend_config.target_params,
                versions_per_param=min_streak + _VERSIONS_BUFFER,
            )
            trends = self._build_degradation_trends(
                bulk_data=bulk_data,
                min_streak=min_streak,
                trend_config=trend_config,
            )

            return DegradationTrendsResponse(
                trends=trends[:limit],
                total_count=len(trends),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Failed to compute degradation trends: %s", e)
            return DegradationTrendsResponse(trends=[], total_count=0)
        except Exception:
            logger.exception("Unexpected error in get_degradation_trends")
            raise

    def _build_degradation_trend_config(
        self,
        parameter_names: list[str] | None,
    ) -> _DegradationTrendConfig:
        """Resolve metric metadata and the subset of parameters eligible for trend checks."""
        eval_modes, all_metrics = self._load_evaluation_modes(parameter_names)
        if parameter_names:
            target_params = [name for name in parameter_names if name in eval_modes]
        else:
            target_params = list(eval_modes.keys())
        return _DegradationTrendConfig(
            target_params=target_params,
            eval_modes=eval_modes,
            all_metrics=all_metrics,
        )

    def _build_degradation_trends(
        self,
        *,
        bulk_data: list[dict[str, Any]],
        min_streak: int,
        trend_config: _DegradationTrendConfig,
    ) -> list[DegradationTrendResponse]:
        """Convert bulk repository results into sorted degradation trends."""
        trends: list[DegradationTrendResponse] = []
        for item in bulk_data:
            trend = self._build_degradation_trend(
                item=item,
                min_streak=min_streak,
                trend_config=trend_config,
            )
            if trend is not None:
                trends.append(trend)

        trends.sort(key=lambda trend: (-trend.streak_count, -abs(trend.total_delta_percent)))
        return trends

    def _build_degradation_trend(
        self,
        *,
        item: dict[str, Any],
        min_streak: int,
        trend_config: _DegradationTrendConfig,
    ) -> DegradationTrendResponse | None:
        """Build one degradation trend response from a bulk-data item."""
        from qdash.common.utils.datetime import ensure_timezone

        param_name = item.get("parameter_name", "")
        versions = item.get("versions", [])
        if param_name not in trend_config.eval_modes or len(versions) < 2:
            return None

        mode = trend_config.eval_modes[param_name]
        streak = self._detect_streak(versions, mode)
        if streak < min_streak:
            return None

        total_delta, total_delta_pct, delta_per_step = self._calculate_trend_metrics(
            versions, streak
        )
        param_meta = trend_config.all_metrics.get(param_name)
        sparkline_values = self._build_degradation_sparkline_values(versions, streak)
        newest_val = versions[0].get("value", 0)

        return DegradationTrendResponse(
            parameter_name=param_name,
            qid=item.get("qid", ""),
            evaluation_mode=mode,
            streak_count=streak,
            total_delta=total_delta,
            total_delta_percent=total_delta_pct,
            delta_per_step=delta_per_step,
            current_value=self._sanitize_value(newest_val),
            current_entity_id=versions[0].get("entity_id", ""),
            unit=param_meta.unit if param_meta else "",
            values=sparkline_values,
            valid_from=ensure_timezone(versions[0].get("valid_from")),
        )

    @staticmethod
    def _build_degradation_sparkline_values(
        versions: list[dict[str, Any]],
        streak: int,
    ) -> list[float]:
        """Build oldest-first numeric values for trend sparklines."""
        sparkline_versions = list(reversed(versions[: streak + 1]))
        return [
            float(version.get("value", 0))
            for version in sparkline_versions
            if isinstance(version.get("value"), (int, float))
        ]

    def _load_evaluation_modes(
        self,
        parameter_names: list[str] | None,
    ) -> tuple[dict[str, str], dict[str, MetricMetadata]]:
        """Load evaluation modes and metric metadata from config.

        Parameters
        ----------
        parameter_names : list[str] | None
            Optional filter — only include these parameter names.

        Returns
        -------
        tuple[dict[str, str], dict[str, MetricMetadata]]
            (eval_modes mapping, all_metrics mapping)

        """
        metrics_config = load_metrics_config()

        eval_modes: dict[str, str] = {}
        all_metrics: dict[str, MetricMetadata] = {}
        for name, meta in metrics_config.qubit_metrics.items():
            if meta.evaluation.mode != "none":
                eval_modes[name] = meta.evaluation.mode
            all_metrics[name] = meta
        for name, meta in metrics_config.coupling_metrics.items():
            if meta.evaluation.mode != "none":
                eval_modes[name] = meta.evaluation.mode
            all_metrics[name] = meta

        return eval_modes, all_metrics

    @staticmethod
    def _detect_streak(versions: list[dict[str, Any]], mode: str) -> int:
        """Count consecutive worsening steps from newest version.

        Parameters
        ----------
        versions : list[dict]
            Versions ordered newest-first.
        mode : str
            ``"maximize"`` or ``"minimize"``.

        Returns
        -------
        int
            Number of consecutive worsening steps.

        """
        streak = 0
        for i in range(len(versions) - 1):
            current_val = versions[i].get("value")
            prev_val = versions[i + 1].get("value")
            if not isinstance(current_val, (int, float)) or not isinstance(prev_val, (int, float)):
                break
            if mode == "maximize":
                is_worse = current_val < prev_val
            else:
                is_worse = current_val > prev_val
            if is_worse:
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _calculate_trend_metrics(
        versions: list[dict[str, Any]], streak: int
    ) -> tuple[float, float, float]:
        """Calculate total_delta, total_delta_percent, and delta_per_step.

        Parameters
        ----------
        versions : list[dict]
            Versions ordered newest-first.
        streak : int
            Number of consecutive worsening steps.

        Returns
        -------
        tuple[float, float, float]
            (total_delta, total_delta_percent, delta_per_step)

        """
        newest_val = versions[0].get("value", 0)
        oldest_val = versions[streak].get("value", 0)
        if isinstance(newest_val, (int, float)) and isinstance(oldest_val, (int, float)):
            total_delta = float(newest_val) - float(oldest_val)
            total_delta_pct = (total_delta / float(oldest_val) * 100) if oldest_val != 0 else 0.0
            delta_per_step = total_delta / streak if streak > 0 else 0.0
        else:
            total_delta = 0.0
            total_delta_pct = 0.0
            delta_per_step = 0.0
        return total_delta, total_delta_pct, delta_per_step

    def get_entity(
        self,
        project_id: str,
        entity_id: str,
    ) -> ParameterVersionResponse | None:
        """Get a specific parameter version by entity ID.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity ID

        Returns
        -------
        ParameterVersionResponse | None
            Parameter version or None if not found

        """
        entity = self.parameter_version_repo.get_by_entity_id(entity_id)
        if entity is None:
            return None
        # Verify project_id matches
        if getattr(entity, "project_id", "") != project_id:
            return None
        return self._build_version_response(entity)

    def get_recalibration_recommendations(
        self,
        project_id: str,
        entity_id: str,
        max_depth: int = 10,
    ) -> RecalibrationRecommendationResponse:
        """Get recalibration task recommendations based on impact analysis.

        When a parameter changes, this method analyzes the impact graph
        to recommend which calibration tasks should be re-run to maintain
        consistency across dependent parameters.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity ID of the changed parameter
        max_depth : int
            Maximum depth for impact traversal (default: 10)

        Returns
        -------
        RecalibrationRecommendationResponse
            Prioritized list of recommended tasks

        """
        source_param_name, source_qid = self._get_recalibration_source_info(entity_id)
        impact_data = self.provenance_relation_repo.get_impact(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )
        recommendation_context = self._build_recalibration_recommendation_context(
            entity_id=entity_id,
            impact_data=impact_data,
            source_param_name=source_param_name,
            source_qid=source_qid,
        )

        return RecalibrationRecommendationResponse(
            source_entity_id=entity_id,
            source_parameter_name=source_param_name,
            source_qid=source_qid,
            recommended_tasks=self._build_recalibration_recommendations(recommendation_context),
            total_affected_parameters=recommendation_context.affected_entity_count,
            max_depth_reached=recommendation_context.max_depth_reached,
        )

    def _get_recalibration_source_info(self, entity_id: str) -> tuple[str, str]:
        """Return the source parameter name and qid for a recommendation request."""
        source_entity = self.parameter_version_repo.get_by_entity_id(entity_id)
        if source_entity is None:
            return "", ""
        return (
            getattr(source_entity, "parameter_name", ""),
            getattr(source_entity, "qid", ""),
        )

    def _build_recalibration_recommendation_context(
        self,
        *,
        entity_id: str,
        impact_data: Any,
        source_param_name: str,
        source_qid: str,
    ) -> _RecalibrationRecommendationContext:
        """Aggregate impact-graph nodes into task-level recommendation inputs."""
        edges = self._build_lineage_edges(impact_data.get("edges", []))
        depths = self._compute_graph_depths(origin_id=entity_id, edges=edges, reverse=True)

        task_info: dict[str, _RecommendationTaskInfo] = {}
        affected_entity_count = 0
        max_depth_reached = 0

        for node_item in impact_data.get("nodes", []):
            node_dict = dict(node_item)
            node_id = str(node_dict.get("id", ""))
            node_depth = depths.get(node_id, 0)
            max_depth_reached = max(max_depth_reached, node_depth)

            node_type = str(node_dict.get("type", ""))
            metadata = cast("dict[str, Any]", node_dict.get("metadata") or {})
            if node_type == "activity":
                self._record_recalibration_activity(task_info, metadata, node_depth)
                continue
            if node_type == "entity":
                if node_id != entity_id:
                    affected_entity_count += 1
                self._record_recalibration_entity(task_info, metadata, node_depth)

        return _RecalibrationRecommendationContext(
            source_param_name=source_param_name,
            source_qid=source_qid,
            task_info=task_info,
            affected_entity_count=affected_entity_count,
            max_depth_reached=max_depth_reached,
        )

    @staticmethod
    def _build_lineage_edges(raw_edges: list[Any]) -> list[LineageEdgeResponse]:
        """Convert raw graph edges into schema responses for depth computation."""
        return [
            LineageEdgeResponse(
                relation_type=str(dict(edge).get("relation_type", "")),
                source_id=str(dict(edge).get("source", "")),
                target_id=str(dict(edge).get("target", "")),
            )
            for edge in raw_edges
        ]

    @staticmethod
    def _get_or_create_recommendation_task(
        task_info: dict[str, _RecommendationTaskInfo],
        task_name: str,
    ) -> _RecommendationTaskInfo:
        """Return the accumulator for one task, creating it on first use."""
        if task_name not in task_info:
            task_info[task_name] = _RecommendationTaskInfo(
                qids=set(),
                parameters=set(),
                min_depth=float("inf"),
            )
        return task_info[task_name]

    def _record_recalibration_activity(
        self,
        task_info: dict[str, _RecommendationTaskInfo],
        metadata: dict[str, Any],
        node_depth: int,
    ) -> None:
        """Record task/qid information from an activity node."""
        task_name = str(metadata.get("task_name", ""))
        if not task_name:
            return
        task_entry = self._get_or_create_recommendation_task(task_info, task_name)
        qid = str(metadata.get("qid", ""))
        if qid:
            task_entry.qids.add(qid)
        task_entry.min_depth = min(task_entry.min_depth, node_depth)

    def _record_recalibration_entity(
        self,
        task_info: dict[str, _RecommendationTaskInfo],
        metadata: dict[str, Any],
        node_depth: int,
    ) -> None:
        """Record affected parameter information from an entity node."""
        task_name = str(metadata.get("task_name", ""))
        param_name = str(metadata.get("parameter_name", ""))
        if not task_name or not param_name:
            return
        task_entry = self._get_or_create_recommendation_task(task_info, task_name)
        task_entry.parameters.add(param_name)
        qid = str(metadata.get("qid", ""))
        if qid:
            task_entry.qids.add(qid)
        task_entry.min_depth = min(task_entry.min_depth, node_depth)
        if task_entry.example is None or node_depth < task_entry.example[2]:
            task_entry.example = (param_name, qid, node_depth)

    def _build_recalibration_recommendations(
        self,
        context: _RecalibrationRecommendationContext,
    ) -> list[RecommendedTaskResponse]:
        """Build sorted recommendation responses from aggregated task info."""
        sorted_tasks = sorted(
            context.task_info.items(),
            key=lambda item: (item[1].min_depth, item[0]),
        )
        return [
            RecommendedTaskResponse(
                task_name=task_name,
                priority=priority,
                affected_parameters=sorted(info.parameters),
                affected_qids=sorted(info.qids),
                reason=self._build_recalibration_reason(info, context),
            )
            for priority, (task_name, info) in enumerate(sorted_tasks, start=1)
        ]

    @staticmethod
    def _build_recalibration_reason(
        info: _RecommendationTaskInfo,
        context: _RecalibrationRecommendationContext,
    ) -> str:
        """Build the explanatory reason text for one recommended task."""
        min_depth = info.min_depth if info.min_depth != float("inf") else 0
        reason_parts = [
            f"Found in impact graph (min depth={min_depth})",
            f"would update {len(info.parameters)} parameter(s)",
        ]
        if context.source_param_name and context.source_qid:
            reason_parts.append(
                f"triggered by {context.source_param_name} ({context.source_qid}) change"
            )
        if info.example is not None:
            param_name, qid, depth = info.example
            reason_parts.append(f"e.g., {param_name} ({qid}) at depth={depth}")
        return "; ".join(reason_parts)

    def _build_version_from_metadata(self, item: dict[str, Any]) -> ParameterVersionResponse | None:
        """Build a ParameterVersionResponse from node metadata.

        Parameters
        ----------
        item : dict
            Node data with metadata

        Returns
        -------
        ParameterVersionResponse | None
            Version response or None

        """
        metadata = item.get("metadata", {})
        if not metadata:
            return None

        from qdash.common.utils.datetime import now

        return ParameterVersionResponse(
            entity_id=item.get("id", ""),
            parameter_name=metadata.get("parameter_name", ""),
            qid=metadata.get("qid", ""),
            value=self._sanitize_value(metadata.get("value", 0)),
            value_type=str(metadata.get("value_type", "float") or "float"),
            unit=metadata.get("unit", ""),
            error=self._sanitize_error(metadata.get("error", 0.0)),
            version=metadata.get("version", 1),
            valid_from=now(),
            valid_until=None,
            execution_id="",
            task_id="",
            task_name=metadata.get("task_name", ""),
            project_id="",
            chip_id="",
        )

    def _build_activity_from_metadata(self, item: dict[str, Any]) -> ActivityResponse | None:
        """Build an ActivityResponse from node metadata.

        Parameters
        ----------
        item : dict
            Node data with metadata

        Returns
        -------
        ActivityResponse | None
            Activity response or None

        """
        metadata = item.get("metadata", {})
        if not metadata:
            return None

        return ActivityResponse(
            activity_id=item.get("id", ""),
            execution_id="",
            task_id=metadata.get("task_id", ""),
            task_name=metadata.get("task_name", ""),
            task_type="",
            qid=metadata.get("qid", ""),
            started_at=None,
            ended_at=None,
            status=metadata.get("status", ""),
            project_id="",
            chip_id="",
        )

    def _sanitize_value(self, value: Any) -> float | int | str:
        """Sanitize values for JSON serialization.

        Converts inf, -inf, nan to 0.0, and None to 0.

        Parameters
        ----------
        value : Any
            Value to sanitize

        Returns
        -------
        float | int | str
            Sanitized value

        """
        if value is None:
            return 0
        if isinstance(value, float):
            if math.isnan(value):
                return 0.0
            if math.isinf(value):
                return 0.0
            return value
        if isinstance(value, (int, str)):
            return value
        return str(value)

    def _sanitize_error(self, value: Any) -> float:
        """Sanitize error values for JSON serialization.

        Parameters
        ----------
        value : Any
            Value to sanitize

        Returns
        -------
        float
            Sanitized float value

        """
        if value is None:
            return 0.0
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return 0.0
            return value
        if isinstance(value, int):
            return float(value)
        return 0.0

    def _build_version_response(self, entity: object) -> ParameterVersionResponse:
        """Build a ParameterVersionResponse from an entity.

        Parameters
        ----------
        entity : object
            Entity document or dict

        Returns
        -------
        ParameterVersionResponse
            Version response object

        """
        from qdash.common.utils.datetime import ensure_timezone

        if isinstance(entity, dict):
            return ParameterVersionResponse(
                entity_id=entity.get("entity_id", ""),
                parameter_name=entity.get("parameter_name", ""),
                qid=entity.get("qid", ""),
                value=self._sanitize_value(entity.get("value", 0)),
                value_type=entity.get("value_type", "float"),
                unit=entity.get("unit", ""),
                error=self._sanitize_error(entity.get("error", 0.0)),
                version=entity.get("version", 1),
                valid_from=ensure_timezone(entity.get("valid_from")),
                valid_until=ensure_timezone(entity.get("valid_until")),
                execution_id=entity.get("execution_id", ""),
                task_id=entity.get("task_id", ""),
                task_name=entity.get("task_name", ""),
                project_id=entity.get("project_id", ""),
                chip_id=entity.get("chip_id", ""),
            )
        return ParameterVersionResponse(
            entity_id=getattr(entity, "entity_id", ""),
            parameter_name=getattr(entity, "parameter_name", ""),
            qid=getattr(entity, "qid", ""),
            value=self._sanitize_value(getattr(entity, "value", 0)),
            value_type=getattr(entity, "value_type", "float"),
            unit=getattr(entity, "unit", ""),
            error=self._sanitize_error(getattr(entity, "error", 0.0)),
            version=getattr(entity, "version", 1),
            valid_from=ensure_timezone(getattr(entity, "valid_from", None)),
            valid_until=ensure_timezone(getattr(entity, "valid_until", None)),
            execution_id=getattr(entity, "execution_id", ""),
            task_id=getattr(entity, "task_id", ""),
            task_name=getattr(entity, "task_name", ""),
            project_id=getattr(entity, "project_id", ""),
            chip_id=getattr(entity, "chip_id", ""),
        )

    def _build_activity_response(self, activity: object) -> ActivityResponse:
        """Build an ActivityResponse from an activity.

        Parameters
        ----------
        activity : object
            Activity document or dict

        Returns
        -------
        ActivityResponse
            Activity response object

        """
        from qdash.common.utils.datetime import ensure_timezone

        if isinstance(activity, dict):
            return ActivityResponse(
                activity_id=activity.get("activity_id", ""),
                execution_id=activity.get("execution_id", ""),
                task_id=activity.get("task_id", ""),
                task_name=activity.get("task_name", ""),
                task_type=activity.get("task_type", ""),
                qid=activity.get("qid", ""),
                started_at=ensure_timezone(activity.get("started_at")),
                ended_at=ensure_timezone(activity.get("ended_at")),
                status=activity.get("status", ""),
                project_id=activity.get("project_id", ""),
                chip_id=activity.get("chip_id", ""),
            )
        return ActivityResponse(
            activity_id=getattr(activity, "activity_id", ""),
            execution_id=getattr(activity, "execution_id", ""),
            task_id=getattr(activity, "task_id", ""),
            task_name=getattr(activity, "task_name", ""),
            task_type=getattr(activity, "task_type", ""),
            qid=getattr(activity, "qid", ""),
            started_at=ensure_timezone(getattr(activity, "started_at", None)),
            ended_at=ensure_timezone(getattr(activity, "ended_at", None)),
            status=getattr(activity, "status", ""),
            project_id=getattr(activity, "project_id", ""),
            chip_id=getattr(activity, "chip_id", ""),
        )
