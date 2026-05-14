"""Shared data-access adapter for Copilot services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from bunnet import SortDirection

if TYPE_CHECKING:
    from qdash.copilot.services.heatmap_service import TaskResultHistoryRepositoryProtocol
    from qdash.copilot.services.provenance_context_service import ProvenanceServiceProtocol
    from qdash.dbmodel.calibration_note import CalibrationNoteDocument
    from qdash.dbmodel.chip import ChipDocument
    from qdash.dbmodel.coupling import CouplingDocument
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument
    from qdash.dbmodel.provenance import ParameterVersionDocument
    from qdash.dbmodel.qubit import QubitDocument
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument


class CopilotDataAccess:
    """Centralized data-access adapter for shared Copilot helpers."""

    def __init__(self, fallback_query_limit: int) -> None:
        self._fallback_query_limit = fallback_query_limit

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

    def build_provenance_service(self) -> ProvenanceServiceProtocol:
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

        return cast("ProvenanceServiceProtocol", _ProvenanceAdapter())

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
            TaskResultHistoryDocument.find(query).limit(self._fallback_query_limit).run(),
        )
