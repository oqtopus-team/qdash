"""Provenance-lineage formatting helpers for Copilot data loading."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable


class ParameterVersionRepositoryProtocol(Protocol):
    """Subset of parameter-version repository behavior used for lineage enrichment."""

    def get_current_many(self, project_id: str, keys: list[tuple[str, str]]) -> list[Any]: ...


class ProvenanceServiceProtocol(Protocol):
    """Subset of provenance-service behavior used for lineage lookups."""

    parameter_version_repo: ParameterVersionRepositoryProtocol

    def get_lineage(self, *, project_id: str, entity_id: str, max_depth: int) -> Any: ...


@dataclass(frozen=True)
class LineageGraphData:
    """Normalized lineage graph payload used for LLM-friendly provenance summaries."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class ProvenanceLineageGraphLoader:
    """Load and format provenance lineage graphs for Copilot tools."""

    def __init__(
        self,
        *,
        resolve_project_id: Callable[[str], str | None],
        get_provenance_service: Callable[[], ProvenanceServiceProtocol],
        compact_number: Callable[[Any], Any],
        compact_timestamp: Callable[[str | None], str],
    ) -> None:
        self._resolve_project_id = resolve_project_id
        self._get_provenance_service = get_provenance_service
        self._compact_number = compact_number
        self._compact_timestamp = compact_timestamp

    def load_provenance_lineage_graph(
        self,
        *,
        entity_id: str,
        chip_id: str,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Load the provenance lineage graph and return an LLM-friendly summary."""
        if not entity_id or entity_id.count(":") != 3:
            return {
                "error": (
                    f"Invalid entity_id format: '{entity_id}'. "
                    "Expected 'parameter_name:qid:execution_id:task_id'."
                )
            }

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

    @staticmethod
    def _compute_graph_depths(
        *,
        origin_id: str,
        edges: list[dict[str, str]],
        reverse: bool,
    ) -> dict[str, int]:
        """Compute shortest-path depths from origin using graph edges."""
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

    def _normalize_lineage_graph_data(self, lineage_data: Any) -> LineageGraphData:
        """Convert lineage service output into a uniform dict-backed graph payload."""
        if isinstance(lineage_data, dict):
            return LineageGraphData(
                nodes=list(lineage_data.get("nodes", [])),
                edges=list(lineage_data.get("edges", [])),
            )

        return LineageGraphData(
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

    def _extract_lineage_node_value(self, metadata: dict[str, Any], node_type: str) -> Any:
        if node_type != "entity":
            return None
        raw_value = metadata.get("value")
        return self._compact_number(raw_value) if raw_value is not None else None

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

    def _extract_lineage_node_valid_from(
        self,
        metadata: dict[str, Any],
        node_type: str,
    ) -> str | None:
        if node_type != "entity" or not metadata.get("valid_from"):
            return None
        return self._compact_timestamp(str(metadata["valid_from"]))

    @staticmethod
    def _extract_lineage_node_status(metadata: dict[str, Any], node_type: str) -> str | None:
        return metadata.get("status") or None if node_type == "activity" else None

    def _enrich_lineage_graph_node_versions(
        self,
        nodes: list[dict[str, Any]],
        parameter_version_repo: ParameterVersionRepositoryProtocol,
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
