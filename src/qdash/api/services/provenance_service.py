"""Provenance service for querying calibration data lineage.

This module provides the ProvenanceService class that handles business logic
for provenance queries, delegating to repositories for data access.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, cast

from qdash.api.lib.metrics_config import MetricMetadata, load_metrics_config
from qdash.api.lib.policy_config import load_policy_config
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
    PolicyViolationResponse,
    PolicyViolationsResponse,
    ProvenanceStatsResponse,
    RecalibrationRecommendationResponse,
    RecentChangesResponse,
    RecentExecutionsResponse,
    RecommendedTaskResponse,
)

if TYPE_CHECKING:
    from qdash.repository.provenance import (
        MongoActivityRepository,
        MongoParameterVersionRepository,
        MongoProvenanceRelationRepository,
    )

logger = logging.getLogger(__name__)


_VERSIONS_BUFFER = 5  # Extra versions to fetch beyond min_streak


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

        nodes: list[LineageNodeResponse] = []
        edges: list[LineageEdgeResponse] = []

        # Convert nodes from LineageGraph format
        for node_item in lineage_data.get("nodes", []):
            node_dict = dict(node_item)  # Convert TypedDict to regular dict
            node = LineageNodeResponse(
                node_type=str(node_dict.get("type", "entity")),
                node_id=str(node_dict.get("id", "")),
                depth=0,
                entity=self._build_version_from_metadata(node_dict)
                if node_dict.get("type") == "entity"
                else None,
                activity=self._build_activity_from_metadata(node_dict)
                if node_dict.get("type") == "activity"
                else None,
            )
            nodes.append(node)

        # Convert edges
        for edge_item in lineage_data.get("edges", []):
            edge_dict = dict(edge_item)  # Convert TypedDict to regular dict
            edges.append(
                LineageEdgeResponse(
                    relation_type=str(edge_dict.get("relation_type", "")),
                    source_id=str(edge_dict.get("source", "")),
                    target_id=str(edge_dict.get("target", "")),
                )
            )

        depths = self._compute_graph_depths(origin_id=entity_id, edges=edges, reverse=False)
        for node in nodes:
            node.depth = depths.get(node.node_id, 0)

        # Find or create origin node
        origin = next(
            (n for n in nodes if n.node_id == entity_id),
            LineageNodeResponse(node_type="entity", node_id=entity_id, depth=0),
        )

        return LineageResponse(
            origin=origin,
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

        nodes: list[LineageNodeResponse] = []
        edges: list[LineageEdgeResponse] = []

        # Convert nodes from LineageGraph format
        for node_item in impact_data.get("nodes", []):
            node_dict = dict(node_item)  # Convert TypedDict to regular dict
            node = LineageNodeResponse(
                node_type=str(node_dict.get("type", "entity")),
                node_id=str(node_dict.get("id", "")),
                depth=0,
                entity=self._build_version_from_metadata(node_dict)
                if node_dict.get("type") == "entity"
                else None,
                activity=self._build_activity_from_metadata(node_dict)
                if node_dict.get("type") == "activity"
                else None,
            )
            nodes.append(node)

        # Convert edges
        for edge_item in impact_data.get("edges", []):
            edge_dict = dict(edge_item)  # Convert TypedDict to regular dict
            edges.append(
                LineageEdgeResponse(
                    relation_type=str(edge_dict.get("relation_type", "")),
                    source_id=str(edge_dict.get("source", "")),
                    target_id=str(edge_dict.get("target", "")),
                )
            )

        depths = self._compute_graph_depths(origin_id=entity_id, edges=edges, reverse=True)
        for node in nodes:
            node.depth = depths.get(node.node_id, 0)

        # Find or create origin node
        origin = next(
            (n for n in nodes if n.node_id == entity_id),
            LineageNodeResponse(node_type="entity", node_id=entity_id, depth=0),
        )

        return ImpactResponse(
            origin=origin,
            nodes=nodes,
            edges=edges,
            max_depth=max_depth,
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

        added: list[ParameterDiffResponse] = []
        removed: list[ParameterDiffResponse] = []
        changed: list[ParameterDiffResponse] = []
        unchanged_count = 0

        for diff in diffs:
            change_type = diff.get("change_type", "")
            before_data = diff.get("before")
            after_data = diff.get("after")

            value_before = before_data.get("value") if before_data else None
            value_after = after_data.get("value") if after_data else None

            # Calculate delta for numeric values
            delta = None
            delta_percent = None
            if (
                change_type == "changed"
                and isinstance(value_before, (int, float))
                and isinstance(value_after, (int, float))
            ):
                delta = value_after - value_before
                if value_before != 0:
                    delta_percent = (delta / value_before) * 100

            param_diff = ParameterDiffResponse(
                parameter_name=diff.get("parameter_name", ""),
                qid=diff.get("qid", ""),
                value_before=value_before,
                value_after=value_after,
                delta=delta,
                delta_percent=delta_percent,
            )

            if change_type == "added":
                added.append(param_diff)
            elif change_type == "removed":
                removed.append(param_diff)
            elif change_type == "changed":
                changed.append(param_diff)

        return ExecutionComparisonResponse(
            execution_id_before=execution_id_before,
            execution_id_after=execution_id_after,
            added_parameters=added,
            removed_parameters=removed,
            changed_parameters=changed,
            unchanged_count=unchanged_count,
        )

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
            from qdash.common.datetime_utils import ensure_timezone

            # Get recent parameter versions (version > 1 means there was a change)
            # Fetch more if filtering by parameter names
            fetch_limit = limit * 5 if parameter_names else limit * 2
            recent_docs = self.parameter_version_repo.get_recent(project_id, limit=fetch_limit)

            changes: list[ParameterChangeResponse] = []

            for doc in recent_docs:
                if len(changes) >= limit:
                    break

                # Filter by parameter names if specified
                if parameter_names and doc.parameter_name not in parameter_names:
                    continue

                # Skip version 1 (first version has no previous)
                current_version = getattr(doc, "version", 1)
                if current_version <= 1:
                    continue

                # Get previous version
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

                # Calculate delta
                delta = None
                delta_percent = None
                if (
                    current_value is not None
                    and previous_value is not None
                    and isinstance(current_value, (int, float))
                    and isinstance(previous_value, (int, float))
                ):
                    delta = float(current_value) - float(previous_value)
                    if previous_value != 0:
                        delta_percent = (delta / float(previous_value)) * 100

                changes.append(
                    ParameterChangeResponse(
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
                )

            return RecentChangesResponse(
                changes=changes,
                total_count=len(changes),
            )
        except Exception as e:
            logger.warning(f"Failed to get recent changes: {e}")
            return RecentChangesResponse(changes=[], total_count=0)

    def get_policy_violations(
        self,
        project_id: str,
        *,
        severity: str | None = None,
        limit: int = 100,
        parameter_names: list[str] | None = None,
    ) -> PolicyViolationsResponse:
        """Evaluate policy rules against current parameter versions."""
        policy = load_policy_config()
        if not policy.rules:
            return PolicyViolationsResponse(violations=[], total_count=0)

        # Pre-index by parameter for fast lookup
        rules_by_parameter: dict[str, list[Any]] = defaultdict(list)
        for rule in policy.rules:
            rules_by_parameter[rule.parameter].append(rule)

        current_versions = self.parameter_version_repo.get_all_current(
            project_id,
            parameter_names=parameter_names,
        )

        violations: list[PolicyViolationResponse] = []
        for doc in current_versions:
            for rule in rules_by_parameter.get(doc.parameter_name, []):
                violations.extend(self._evaluate_policy_rule(doc, rule))

        if severity in {"warn", "error"}:
            violations = [v for v in violations if v.severity == severity]

        # Sort: newest first
        violations.sort(
            key=lambda v: (
                -(v.valid_from.timestamp() if v.valid_from else 0),
                v.parameter_name,
                v.qid,
                v.check_type,
            )
        )

        return PolicyViolationsResponse(
            violations=violations[:limit],
            total_count=len(violations),
        )

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
            from qdash.common.datetime_utils import ensure_timezone

            eval_modes, all_metrics = self._load_evaluation_modes(parameter_names)

            # Determine target parameters
            if parameter_names:
                target_params = [p for p in parameter_names if p in eval_modes]
            else:
                target_params = list(eval_modes.keys())

            if not target_params:
                return DegradationTrendsResponse(trends=[], total_count=0)

            # Bulk fetch recent versions
            bulk_data = self.parameter_version_repo.get_recent_versions_bulk(
                project_id,
                parameter_names=target_params,
                versions_per_param=min_streak + _VERSIONS_BUFFER,
            )

            trends: list[DegradationTrendResponse] = []

            for item in bulk_data:
                param_name = item.get("parameter_name", "")
                qid = item.get("qid", "")
                versions = item.get("versions", [])

                if param_name not in eval_modes:
                    continue
                if len(versions) < 2:
                    continue

                mode = eval_modes[param_name]
                streak = self._detect_streak(versions, mode)

                if streak < min_streak:
                    continue

                total_delta, total_delta_pct, delta_per_step = self._calculate_trend_metrics(
                    versions, streak
                )

                # Build sparkline values (oldest first, i.e. reverse of versions[:streak+1])
                sparkline_versions = versions[: streak + 1]
                sparkline_versions.reverse()
                values = [
                    float(v.get("value", 0))
                    for v in sparkline_versions
                    if isinstance(v.get("value"), (int, float))
                ]

                param_meta = all_metrics.get(param_name)
                unit = param_meta.unit if param_meta else ""
                newest_val = versions[0].get("value", 0)

                trends.append(
                    DegradationTrendResponse(
                        parameter_name=param_name,
                        qid=qid,
                        evaluation_mode=mode,
                        streak_count=streak,
                        total_delta=total_delta,
                        total_delta_percent=total_delta_pct,
                        delta_per_step=delta_per_step,
                        current_value=self._sanitize_value(newest_val),
                        current_entity_id=versions[0].get("entity_id", ""),
                        unit=unit,
                        values=values,
                        valid_from=ensure_timezone(versions[0].get("valid_from")),
                    )
                )

            # Sort: streak descending, then |total_delta_percent| descending
            trends.sort(
                key=lambda t: (-t.streak_count, -abs(t.total_delta_percent)),
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

    def get_policy_impact_violations(
        self,
        project_id: str,
        *,
        entity_id: str,
        max_depth: int = 10,
        severity: str | None = None,
        limit: int = 200,
    ) -> PolicyViolationsResponse:
        """Evaluate policy rules for current versions within the impact set of an entity."""
        impact = self.get_impact(project_id=project_id, entity_id=entity_id, max_depth=max_depth)

        pairs: set[tuple[str, str]] = set()
        for node in impact.nodes:
            if node.node_type != "entity":
                continue
            if not node.entity:
                continue
            pairs.add((node.entity.parameter_name, node.entity.qid))

        current_docs = self.parameter_version_repo.get_current_many(
            project_id,
            keys=sorted(pairs),
        )

        policy = load_policy_config()
        if not policy.rules:
            return PolicyViolationsResponse(violations=[], total_count=0)

        rules_by_parameter: dict[str, list[Any]] = defaultdict(list)
        for rule in policy.rules:
            rules_by_parameter[rule.parameter].append(rule)

        violations: list[PolicyViolationResponse] = []
        for doc in current_docs:
            for rule in rules_by_parameter.get(doc.parameter_name, []):
                violations.extend(self._evaluate_policy_rule(doc, rule))

        if severity in {"warn", "error"}:
            violations = [v for v in violations if v.severity == severity]

        violations.sort(
            key=lambda v: (
                -(v.valid_from.timestamp() if v.valid_from else 0),
                v.parameter_name,
                v.qid,
                v.check_type,
            )
        )

        return PolicyViolationsResponse(
            violations=violations[:limit],
            total_count=len(violations),
        )

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _evaluate_policy_rule(self, doc: Any, rule: Any) -> list[PolicyViolationResponse]:
        from datetime import datetime, timezone

        from qdash.common.datetime_utils import ensure_timezone

        results: list[PolicyViolationResponse] = []

        value_num = self._safe_float(getattr(doc, "value", None))
        error_num = self._safe_float(getattr(doc, "error", None)) or 0.0
        valid_from = getattr(doc, "valid_from", None)
        if valid_from:
            valid_from = ensure_timezone(valid_from)

        now = datetime.now(timezone.utc)

        for check in getattr(rule, "checks", []):
            check_type = check.type
            measured: float | None = None
            violates_warn = False

            if check_type in {"min", "max"}:
                if value_num is None:
                    continue
                measured = value_num
                if check_type == "min":
                    violates_warn = value_num < check.warn
                elif check_type == "max":
                    violates_warn = value_num > check.warn

            elif check_type == "staleness_hours":
                if not valid_from:
                    continue
                age_hours = (now - valid_from).total_seconds() / 3600.0
                measured = age_hours
                violates_warn = age_hours >= check.warn

            elif check_type == "uncertainty_ratio":
                if value_num is None or value_num == 0:
                    continue
                measured = abs(error_num / value_num)
                violates_warn = measured >= check.warn

            else:
                continue

            if not violates_warn:
                continue

            severity = "warn"

            results.append(
                PolicyViolationResponse(
                    entity_id=getattr(doc, "entity_id", ""),
                    parameter_name=getattr(doc, "parameter_name", ""),
                    qid=getattr(doc, "qid", "") or "",
                    value=getattr(doc, "value", ""),
                    unit=getattr(doc, "unit", "") or "",
                    error=float(error_num),
                    valid_from=valid_from,
                    severity=severity,
                    check_type=check_type,
                    message=check.message or "",
                    warn_threshold=float(check.warn),
                    measured=measured,
                )
            )

        return results

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
        # Get the source entity info
        source_entity = self.parameter_version_repo.get_by_entity_id(entity_id)
        source_param_name = ""
        source_qid = ""
        if source_entity:
            source_param_name = getattr(source_entity, "parameter_name", "")
            source_qid = getattr(source_entity, "qid", "")

        # Get impact graph
        impact_data = self.provenance_relation_repo.get_impact(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )

        edges: list[LineageEdgeResponse] = [
            LineageEdgeResponse(
                relation_type=str(dict(e).get("relation_type", "")),
                source_id=str(dict(e).get("source", "")),
                target_id=str(dict(e).get("target", "")),
            )
            for e in impact_data.get("edges", [])
        ]
        depths = self._compute_graph_depths(origin_id=entity_id, edges=edges, reverse=True)

        # Extract activities and their affected parameters from the impact graph.
        # task_name -> {qids: set, parameters: set, min_depth: int, example: tuple | None}
        task_info: dict[str, dict[str, Any]] = {}
        affected_entity_count = 0
        max_depth_reached = 0

        for node_item in impact_data.get("nodes", []):
            node_dict = dict(node_item)
            node_type = str(node_dict.get("type", ""))
            metadata = cast(dict[str, Any], node_dict.get("metadata") or {})
            node_id = str(node_dict.get("id", ""))
            node_depth = depths.get(node_id, 0)
            max_depth_reached = max(max_depth_reached, node_depth)

            if node_type == "activity":
                task_name = str(metadata.get("task_name", ""))
                qid = str(metadata.get("qid", ""))
                if task_name:
                    if task_name not in task_info:
                        task_info[task_name] = {
                            "qids": set(),
                            "parameters": set(),
                            "min_depth": float("inf"),
                            "example": None,  # (param_name, qid, depth)
                        }
                    if qid:
                        task_info[task_name]["qids"].add(qid)
                    task_info[task_name]["min_depth"] = min(
                        task_info[task_name]["min_depth"], node_depth
                    )

            elif node_type == "entity":
                # Count affected entities (excluding source)
                if node_id != entity_id:
                    affected_entity_count += 1

                # Track which parameters each task affects
                param_name = str(metadata.get("parameter_name", ""))
                task_name = str(metadata.get("task_name", ""))
                qid = str(metadata.get("qid", ""))
                if task_name and param_name:
                    if task_name not in task_info:
                        task_info[task_name] = {
                            "qids": set(),
                            "parameters": set(),
                            "min_depth": float("inf"),
                            "example": None,  # (param_name, qid, depth)
                        }
                    task_info[task_name]["parameters"].add(param_name)
                    if qid:
                        task_info[task_name]["qids"].add(qid)
                    task_info[task_name]["min_depth"] = min(
                        task_info[task_name]["min_depth"], node_depth
                    )
                    ex = task_info[task_name]["example"]
                    if ex is None or node_depth < ex[2]:
                        task_info[task_name]["example"] = (param_name, qid, node_depth)

        # Build recommendations sorted by proximity (min_depth)
        sorted_tasks = sorted(
            task_info.items(),
            key=lambda x: (x[1]["min_depth"], x[0]),
        )

        recommendations = []
        for priority, (task_name, info) in enumerate(sorted_tasks, start=1):
            qids = sorted(info["qids"])
            params = sorted(info["parameters"])
            min_depth = info["min_depth"] if info["min_depth"] != float("inf") else 0

            reason_parts = [
                f"Found in impact graph (min depth={min_depth})",
                f"would update {len(params)} parameter(s)",
            ]
            if source_param_name and source_qid:
                reason_parts.append(f"triggered by {source_param_name} ({source_qid}) change")
            example = info.get("example")
            if example is not None:
                ex_param, ex_qid, ex_depth = example
                reason_parts.append(f"e.g., {ex_param} ({ex_qid}) at depth={ex_depth}")
            reason = "; ".join(reason_parts)

            recommendations.append(
                RecommendedTaskResponse(
                    task_name=task_name,
                    priority=priority,
                    affected_parameters=params,
                    affected_qids=qids,
                    reason=reason,
                )
            )

        return RecalibrationRecommendationResponse(
            source_entity_id=entity_id,
            source_parameter_name=source_param_name,
            source_qid=source_qid,
            recommended_tasks=recommendations,
            total_affected_parameters=affected_entity_count,
            max_depth_reached=max_depth_reached,
        )

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

        from qdash.common.datetime_utils import now

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
        from qdash.common.datetime_utils import ensure_timezone

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
        from qdash.common.datetime_utils import ensure_timezone

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
