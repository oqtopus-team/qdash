"""MongoDB implementation of Provenance repositories.

This module provides concrete MongoDB implementations for provenance
data persistence and querying operations.

Key features:
- Parameter version tracking
- Provenance relation management
- Lineage and impact graph traversal
- Execution comparison
"""

import logging
from datetime import datetime
from typing import Any, Literal, TypedDict

from bunnet import SortDirection
from qdash.common.datetime_utils import now
from qdash.dbmodel.provenance import (
    ActivityDocument,
    ParameterVersionDocument,
    ProvenanceRelationDocument,
    ProvenanceRelationType,
)

logger = logging.getLogger(__name__)


class LineageNode(TypedDict):
    """Node in a lineage graph."""

    id: str
    type: Literal["entity", "activity"]
    name: str
    metadata: dict[str, Any]


class LineageEdge(TypedDict):
    """Edge in a lineage graph."""

    source: str
    target: str
    relation_type: str


class LineageGraph(TypedDict):
    """Complete lineage graph."""

    nodes: list[LineageNode]
    edges: list[LineageEdge]


class ParameterDiff(TypedDict):
    """Difference between two parameter versions."""

    parameter_name: str
    qid: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    change_type: Literal["added", "removed", "changed"]


class MongoParameterVersionRepository:
    """MongoDB implementation for parameter version persistence.

    This repository handles versioned parameter storage and retrieval,
    supporting the Entity concept from W3C PROV-DM.

    Example
    -------
        >>> repo = MongoParameterVersionRepository()
        >>> entity = repo.create_version(
        ...     parameter_name="qubit_frequency",
        ...     qid="Q0",
        ...     value=5.123,
        ...     unit="GHz",
        ...     execution_id="20241224-001",
        ...     task_id="task-001",
        ...     project_id="proj-1",
        ... )

    """

    def create_version(
        self,
        *,
        parameter_name: str,
        qid: str,
        value: float | int | str,
        execution_id: str,
        task_id: str,
        project_id: str,
        task_name: str = "",
        chip_id: str = "",
        unit: str = "",
        error: float = 0.0,
        value_type: str = "float",
    ) -> ParameterVersionDocument:
        """Create a new parameter version.

        This method:
        1. Invalidates any current version
        2. Gets the next version number
        3. Creates the new version document

        Parameters
        ----------
        parameter_name : str
            Name of the parameter
        qid : str
            Qubit or coupling identifier
        value : float | int | str
            Parameter value
        execution_id : str
            Execution ID
        task_id : str
            Task ID
        project_id : str
            Project identifier
        task_name : str
            Name of the producing task
        chip_id : str
            Chip identifier
        unit : str
            Physical unit
        error : float
            Measurement error
        value_type : str
            Type of value

        Returns
        -------
        ParameterVersionDocument
            The created version document

        """
        # Invalidate current version
        current_time = now()
        ParameterVersionDocument.invalidate_current(
            project_id=project_id,
            parameter_name=parameter_name,
            qid=qid,
            invalidated_at=current_time,
        )

        # Get next version number
        next_version = ParameterVersionDocument.get_next_version(
            project_id=project_id,
            parameter_name=parameter_name,
            qid=qid,
        )

        # Generate entity ID
        entity_id = ParameterVersionDocument.generate_entity_id(
            parameter_name=parameter_name,
            qid=qid,
            execution_id=execution_id,
            task_id=task_id,
        )

        # Create new version
        doc = ParameterVersionDocument(
            entity_id=entity_id,
            parameter_name=parameter_name,
            qid=qid,
            value=value,
            value_type=value_type,
            unit=unit,
            error=error,
            version=next_version,
            valid_from=current_time,
            valid_until=None,
            execution_id=execution_id,
            task_id=task_id,
            task_name=task_name,
            project_id=project_id,
            chip_id=chip_id,
        )
        doc.insert()
        return doc

    def get_current(
        self,
        project_id: str,
        parameter_name: str,
        qid: str,
    ) -> ParameterVersionDocument | None:
        """Get the current version of a parameter.

        Parameters
        ----------
        project_id : str
            Project identifier
        parameter_name : str
            Parameter name
        qid : str
            Qubit or coupling identifier

        Returns
        -------
        ParameterVersionDocument | None
            Current version or None

        """
        result: ParameterVersionDocument | None = ParameterVersionDocument.get_current_version(
            project_id=project_id,
            parameter_name=parameter_name,
            qid=qid,
        )
        return result

    def get_by_entity_id(self, entity_id: str) -> ParameterVersionDocument | None:
        """Get a parameter version by entity ID.

        Parameters
        ----------
        entity_id : str
            Entity identifier

        Returns
        -------
        ParameterVersionDocument | None
            Parameter version or None

        """
        return ParameterVersionDocument.find_one({"entity_id": entity_id}).run()

    def get_version_history(
        self,
        project_id: str,
        parameter_name: str,
        qid: str,
        limit: int = 100,
    ) -> list[ParameterVersionDocument]:
        """Get version history for a parameter.

        Parameters
        ----------
        project_id : str
            Project identifier
        parameter_name : str
            Parameter name
        qid : str
            Qubit or coupling identifier
        limit : int
            Maximum number of versions to return

        Returns
        -------
        list[ParameterVersionDocument]
            List of versions, newest first

        """
        return list(
            ParameterVersionDocument.find(
                {
                    "project_id": project_id,
                    "parameter_name": parameter_name,
                    "qid": qid,
                }
            )
            .sort([("version", SortDirection.DESCENDING)])
            .limit(limit)
            .run()
        )

    def get_version(
        self,
        project_id: str,
        parameter_name: str,
        qid: str,
        version: int,
    ) -> ParameterVersionDocument | None:
        """Get a specific version of a parameter.

        Parameters
        ----------
        project_id : str
            Project identifier
        parameter_name : str
            Parameter name
        qid : str
            Qubit or coupling identifier
        version : int
            Version number to retrieve

        Returns
        -------
        ParameterVersionDocument | None
            The specific version, or None if not found

        """
        return ParameterVersionDocument.find_one(
            {
                "project_id": project_id,
                "parameter_name": parameter_name,
                "qid": qid,
                "version": version,
            }
        ).run()

    def get_by_execution(
        self,
        project_id: str,
        execution_id: str,
    ) -> list[ParameterVersionDocument]:
        """Get all parameter versions from an execution.

        Parameters
        ----------
        project_id : str
            Project identifier
        execution_id : str
            Execution ID

        Returns
        -------
        list[ParameterVersionDocument]
            List of parameter versions

        """
        return list(
            ParameterVersionDocument.find(
                {
                    "project_id": project_id,
                    "execution_id": execution_id,
                }
            ).run()
        )

    def get_by_task(
        self,
        project_id: str,
        task_id: str,
    ) -> list[ParameterVersionDocument]:
        """Get all parameter versions from a task.

        Parameters
        ----------
        project_id : str
            Project identifier
        task_id : str
            Task ID

        Returns
        -------
        list[ParameterVersionDocument]
            List of parameter versions

        """
        return list(
            ParameterVersionDocument.find(
                {
                    "project_id": project_id,
                    "task_id": task_id,
                }
            ).run()
        )

    def count(self, project_id: str) -> int:
        """Count parameter versions for a project.

        Parameters
        ----------
        project_id : str
            Project identifier

        Returns
        -------
        int
            Number of parameter versions

        """
        return ParameterVersionDocument.find({"project_id": project_id}).count()

    def get_recent(
        self,
        project_id: str,
        limit: int = 10,
    ) -> list[ParameterVersionDocument]:
        """Get the most recent parameter versions.

        Parameters
        ----------
        project_id : str
            Project identifier
        limit : int
            Maximum number of versions to return

        Returns
        -------
        list[ParameterVersionDocument]
            List of recent parameter versions

        """
        return list(
            ParameterVersionDocument.find({"project_id": project_id})
            .sort([("valid_from", SortDirection.DESCENDING)])
            .limit(limit)
            .run()
        )

    def get_recent_execution_ids(
        self,
        project_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get unique execution IDs sorted by most recent.

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
        list[dict[str, Any]]
            List of dicts with execution_id and latest valid_from

        """
        pipeline = [
            {"$match": {"project_id": project_id}},
            {
                "$group": {
                    "_id": "$execution_id",
                    "latest_valid_from": {"$max": "$valid_from"},
                }
            },
            {"$sort": {"latest_valid_from": -1}},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "execution_id": "$_id",
                    "valid_from": "$latest_valid_from",
                }
            },
        ]
        return list(ParameterVersionDocument.aggregate(pipeline).run())


class MongoProvenanceRelationRepository:
    """MongoDB implementation for provenance relation persistence.

    This repository handles provenance relationships between entities
    and activities, supporting graph traversal for lineage and impact analysis.

    Example
    -------
        >>> repo = MongoProvenanceRelationRepository()
        >>> repo.create_relation(
        ...     relation_type=ProvenanceRelationType.GENERATED_BY,
        ...     source_type="entity",
        ...     source_id="qubit_frequency:Q0:exec001:task001",
        ...     target_type="activity",
        ...     target_id="exec001:task001",
        ...     project_id="proj-1",
        ... )

    """

    def create_relation(
        self,
        *,
        relation_type: ProvenanceRelationType,
        source_type: Literal["entity", "activity"],
        source_id: str,
        target_type: Literal["entity", "activity"],
        target_id: str,
        project_id: str,
        execution_id: str = "",
    ) -> ProvenanceRelationDocument:
        """Create a provenance relation.

        Parameters
        ----------
        relation_type : ProvenanceRelationType
            Type of relation
        source_type : Literal["entity", "activity"]
            Source node type
        source_id : str
            Source identifier
        target_type : Literal["entity", "activity"]
            Target node type
        target_id : str
            Target identifier
        project_id : str
            Project identifier
        execution_id : str
            Related execution ID

        Returns
        -------
        ProvenanceRelationDocument
            Created relation

        """
        result: ProvenanceRelationDocument = ProvenanceRelationDocument.create_relation(
            relation_type=relation_type,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            project_id=project_id,
            execution_id=execution_id,
        )
        return result

    def get_relations_from(
        self,
        project_id: str,
        source_type: Literal["entity", "activity"],
        source_id: str,
        relation_types: list[ProvenanceRelationType] | None = None,
    ) -> list[ProvenanceRelationDocument]:
        """Get relations from a source node (forward traversal).

        Parameters
        ----------
        project_id : str
            Project identifier
        source_type : Literal["entity", "activity"]
            Source node type
        source_id : str
            Source identifier
        relation_types : list[ProvenanceRelationType] | None
            Filter by relation types

        Returns
        -------
        list[ProvenanceRelationDocument]
            List of relations

        """
        query: dict[str, Any] = {
            "project_id": project_id,
            "source_type": source_type,
            "source_id": source_id,
        }
        if relation_types:
            query["relation_type"] = {"$in": [rt.value for rt in relation_types]}

        return list(ProvenanceRelationDocument.find(query).run())

    def get_relations_to(
        self,
        project_id: str,
        target_type: Literal["entity", "activity"],
        target_id: str,
        relation_types: list[ProvenanceRelationType] | None = None,
    ) -> list[ProvenanceRelationDocument]:
        """Get relations to a target node (backward traversal).

        Parameters
        ----------
        project_id : str
            Project identifier
        target_type : Literal["entity", "activity"]
            Target node type
        target_id : str
            Target identifier
        relation_types : list[ProvenanceRelationType] | None
            Filter by relation types

        Returns
        -------
        list[ProvenanceRelationDocument]
            List of relations

        """
        query: dict[str, Any] = {
            "project_id": project_id,
            "target_type": target_type,
            "target_id": target_id,
        }
        if relation_types:
            query["relation_type"] = {"$in": [rt.value for rt in relation_types]}

        return list(ProvenanceRelationDocument.find(query).run())

    def get_lineage(
        self,
        project_id: str,
        entity_id: str,
        max_depth: int = 5,
    ) -> LineageGraph:
        """Get the lineage (ancestors) of an entity.

        Traverses wasDerivedFrom and wasGeneratedBy relations backward
        to find all entities and activities that contributed to this entity.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity to trace lineage for
        max_depth : int
            Maximum traversal depth

        Returns
        -------
        LineageGraph
            Graph of nodes and edges

        """
        nodes: dict[str, LineageNode] = {}
        edges: list[LineageEdge] = []
        visited: set[str] = set()

        def traverse(node_id: str, node_type: Literal["entity", "activity"], depth: int) -> None:
            if depth > max_depth or node_id in visited:
                return
            visited.add(node_id)

            # Add node
            if node_id not in nodes:
                nodes[node_id] = self._create_node(project_id, node_id, node_type)

            # Get backward relations
            if node_type == "entity":
                # Entity: look for wasGeneratedBy (to activity) and wasDerivedFrom (to entity)
                relations = self.get_relations_from(
                    project_id=project_id,
                    source_type="entity",
                    source_id=node_id,
                    relation_types=[
                        ProvenanceRelationType.GENERATED_BY,
                        ProvenanceRelationType.DERIVED_FROM,
                    ],
                )
                for rel in relations:
                    edges.append(
                        LineageEdge(
                            source=node_id,
                            target=rel.target_id,
                            relation_type=rel.relation_type.value,
                        )
                    )
                    traverse(rel.target_id, rel.target_type, depth + 1)

            else:  # activity
                # Activity: look for used (to entity)
                relations = self.get_relations_from(
                    project_id=project_id,
                    source_type="activity",
                    source_id=node_id,
                    relation_types=[ProvenanceRelationType.USED],
                )
                for rel in relations:
                    edges.append(
                        LineageEdge(
                            source=node_id,
                            target=rel.target_id,
                            relation_type=rel.relation_type.value,
                        )
                    )
                    traverse(rel.target_id, rel.target_type, depth + 1)

        traverse(entity_id, "entity", 0)
        return LineageGraph(nodes=list(nodes.values()), edges=edges)

    def get_impact(
        self,
        project_id: str,
        entity_id: str,
        max_depth: int = 5,
    ) -> LineageGraph:
        """Get the impact (descendants) of an entity.

        Traverses wasDerivedFrom relations forward to find all entities
        that were derived from this entity.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity to trace impact for
        max_depth : int
            Maximum traversal depth

        Returns
        -------
        LineageGraph
            Graph of nodes and edges

        """
        nodes: dict[str, LineageNode] = {}
        edges: list[LineageEdge] = []
        visited: set[str] = set()

        def traverse(node_id: str, node_type: Literal["entity", "activity"], depth: int) -> None:
            if depth > max_depth or node_id in visited:
                return
            visited.add(node_id)

            # Add node
            if node_id not in nodes:
                nodes[node_id] = self._create_node(project_id, node_id, node_type)

            # Get forward relations (reverse of lineage)
            if node_type == "entity":
                # Find entities that were derived from this entity
                relations = self.get_relations_to(
                    project_id=project_id,
                    target_type="entity",
                    target_id=node_id,
                    relation_types=[ProvenanceRelationType.DERIVED_FROM],
                )
                for rel in relations:
                    edges.append(
                        LineageEdge(
                            source=rel.source_id,
                            target=node_id,
                            relation_type=rel.relation_type.value,
                        )
                    )
                    traverse(rel.source_id, rel.source_type, depth + 1)

                # Find activities that used this entity
                relations = self.get_relations_to(
                    project_id=project_id,
                    target_type="entity",
                    target_id=node_id,
                    relation_types=[ProvenanceRelationType.USED],
                )
                for rel in relations:
                    edges.append(
                        LineageEdge(
                            source=rel.source_id,
                            target=node_id,
                            relation_type=rel.relation_type.value,
                        )
                    )
                    traverse(rel.source_id, rel.source_type, depth + 1)

            else:  # activity
                # Find entities generated by this activity
                relations = self.get_relations_to(
                    project_id=project_id,
                    target_type="activity",
                    target_id=node_id,
                    relation_types=[ProvenanceRelationType.GENERATED_BY],
                )
                for rel in relations:
                    edges.append(
                        LineageEdge(
                            source=rel.source_id,
                            target=node_id,
                            relation_type=rel.relation_type.value,
                        )
                    )
                    traverse(rel.source_id, rel.source_type, depth + 1)

        traverse(entity_id, "entity", 0)
        return LineageGraph(nodes=list(nodes.values()), edges=edges)

    def _create_node(
        self,
        project_id: str,
        node_id: str,
        node_type: Literal["entity", "activity"],
    ) -> LineageNode:
        """Create a node for the lineage graph.

        Parameters
        ----------
        project_id : str
            Project identifier
        node_id : str
            Node identifier
        node_type : Literal["entity", "activity"]
            Type of node

        Returns
        -------
        LineageNode
            Node data

        """
        metadata: dict[str, Any] = {}
        name = node_id

        if node_type == "entity":
            entity = ParameterVersionDocument.find_one({"entity_id": node_id}).run()
            if entity:
                name = f"{entity.parameter_name} ({entity.qid})"
                metadata = {
                    "parameter_name": entity.parameter_name,
                    "qid": entity.qid,
                    "value": entity.value,
                    "unit": entity.unit,
                    "version": entity.version,
                    "task_name": entity.task_name,
                }
        else:  # activity
            activity = ActivityDocument.find_one({"activity_id": node_id}).run()
            if activity:
                name = f"{activity.task_name} ({activity.qid})"
                metadata = {
                    "task_name": activity.task_name,
                    "task_id": activity.task_id,
                    "qid": activity.qid,
                    "status": activity.status,
                }

        return LineageNode(
            id=node_id,
            type=node_type,
            name=name,
            metadata=metadata,
        )

    def compare_executions(
        self,
        project_id: str,
        execution_id_1: str,
        execution_id_2: str,
    ) -> list[ParameterDiff]:
        """Compare parameter versions between two executions.

        Parameters
        ----------
        project_id : str
            Project identifier
        execution_id_1 : str
            First execution ID (before)
        execution_id_2 : str
            Second execution ID (after)

        Returns
        -------
        list[ParameterDiff]
            List of differences

        """
        param_repo = MongoParameterVersionRepository()

        params_1 = param_repo.get_by_execution(project_id, execution_id_1)
        params_2 = param_repo.get_by_execution(project_id, execution_id_2)

        # Index by (parameter_name, qid)
        map_1: dict[tuple[str, str], ParameterVersionDocument] = {
            (p.parameter_name, p.qid): p for p in params_1
        }
        map_2: dict[tuple[str, str], ParameterVersionDocument] = {
            (p.parameter_name, p.qid): p for p in params_2
        }

        all_keys = set(map_1.keys()) | set(map_2.keys())
        diffs: list[ParameterDiff] = []

        for key in all_keys:
            param_name, qid = key
            p1 = map_1.get(key)
            p2 = map_2.get(key)

            if p1 is None:
                diffs.append(
                    ParameterDiff(
                        parameter_name=param_name,
                        qid=qid,
                        before=None,
                        after={"value": p2.value, "version": p2.version} if p2 else None,
                        change_type="added",
                    )
                )
            elif p2 is None:
                diffs.append(
                    ParameterDiff(
                        parameter_name=param_name,
                        qid=qid,
                        before={"value": p1.value, "version": p1.version},
                        after=None,
                        change_type="removed",
                    )
                )
            elif p1.value != p2.value:
                diffs.append(
                    ParameterDiff(
                        parameter_name=param_name,
                        qid=qid,
                        before={"value": p1.value, "version": p1.version},
                        after={"value": p2.value, "version": p2.version},
                        change_type="changed",
                    )
                )

        return diffs

    def count(self, project_id: str) -> int:
        """Count provenance relations for a project.

        Parameters
        ----------
        project_id : str
            Project identifier

        Returns
        -------
        int
            Number of relations

        """
        return ProvenanceRelationDocument.find({"project_id": project_id}).count()

    def count_by_type(self, project_id: str) -> dict[str, int]:
        """Count relations by type for a project.

        Parameters
        ----------
        project_id : str
            Project identifier

        Returns
        -------
        dict[str, int]
            Counts by relation type

        """
        counts: dict[str, int] = {}
        for rel_type in ProvenanceRelationType:
            count = ProvenanceRelationDocument.find(
                {"project_id": project_id, "relation_type": rel_type.value}
            ).count()
            if count > 0:
                counts[rel_type.value] = count
        return counts


class MongoActivityRepository:
    """MongoDB implementation for activity persistence.

    This repository handles activity (task execution) records for
    provenance tracking.
    """

    def create_activity(
        self,
        *,
        execution_id: str,
        task_id: str,
        task_name: str,
        project_id: str,
        task_type: str = "",
        qid: str = "",
        chip_id: str = "",
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        status: str = "",
    ) -> ActivityDocument:
        """Create an activity record.

        Parameters
        ----------
        execution_id : str
            Parent execution ID
        task_id : str
            Task identifier
        task_name : str
            Name of the task
        project_id : str
            Project identifier
        task_type : str
            Type of task
        qid : str
            Qubit or coupling identifier
        chip_id : str
            Chip identifier
        started_at : datetime | None
            Start time
        ended_at : datetime | None
            End time
        status : str
            Execution status

        Returns
        -------
        ActivityDocument
            Created activity

        """
        activity_id = ActivityDocument.generate_activity_id(execution_id, task_id)

        # Check for existing
        existing = ActivityDocument.find_one({"activity_id": activity_id}).run()
        if existing:
            # Update existing
            existing.task_name = task_name
            existing.task_type = task_type
            existing.qid = qid
            existing.chip_id = chip_id
            existing.started_at = started_at
            existing.ended_at = ended_at
            existing.status = status
            existing.save()
            return existing

        # Create new
        activity = ActivityDocument(
            activity_id=activity_id,
            execution_id=execution_id,
            task_id=task_id,
            task_name=task_name,
            task_type=task_type,
            qid=qid,
            project_id=project_id,
            chip_id=chip_id,
            started_at=started_at,
            ended_at=ended_at,
            status=status,
        )
        activity.insert()
        return activity

    def get_by_id(self, activity_id: str) -> ActivityDocument | None:
        """Get an activity by ID.

        Parameters
        ----------
        activity_id : str
            Activity identifier

        Returns
        -------
        ActivityDocument | None
            Activity or None

        """
        return ActivityDocument.find_one({"activity_id": activity_id}).run()

    def get_by_execution(
        self,
        project_id: str,
        execution_id: str,
    ) -> list[ActivityDocument]:
        """Get all activities for an execution.

        Parameters
        ----------
        project_id : str
            Project identifier
        execution_id : str
            Execution ID

        Returns
        -------
        list[ActivityDocument]
            List of activities

        """
        return list(
            ActivityDocument.find(
                {
                    "project_id": project_id,
                    "execution_id": execution_id,
                }
            )
            .sort([("started_at", SortDirection.ASCENDING)])
            .run()
        )

    def count(self, project_id: str) -> int:
        """Count activities for a project.

        Parameters
        ----------
        project_id : str
            Project identifier

        Returns
        -------
        int
            Number of activities

        """
        return ActivityDocument.find({"project_id": project_id}).count()
