"""Service that writes qubit calibration output parameters chosen by a human.

This is the task-agnostic half of the reanalysis flow: taking output-parameter values,
writing them to the calibration DB, and recording a task-result history row so the
manual edit stays traceable. Reanalysis reuses the same commit path for its own values.
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from fastapi import HTTPException

from qdash.common.utils.datetime import now
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.provenance import ProvenanceRelationType
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.provenance import (
    MongoActivityRepository,
    MongoParameterVersionRepository,
    MongoProvenanceRelationRepository,
)
from qdash.repository.qubit import MongoQubitCalibrationRepository


class QubitParameterService:
    """Persist qubit output parameters and record where they came from."""

    def __init__(
        self,
        qubit_repo: MongoQubitCalibrationRepository | None = None,
        activity_repo: MongoActivityRepository | None = None,
        param_version_repo: MongoParameterVersionRepository | None = None,
        relation_repo: MongoProvenanceRelationRepository | None = None,
    ) -> None:
        self._qubit_repo = qubit_repo or MongoQubitCalibrationRepository()
        self._activity_repo = activity_repo or MongoActivityRepository()
        self._param_version_repo = param_version_repo or MongoParameterVersionRepository()
        self._relation_repo = relation_repo or MongoProvenanceRelationRepository()

    def commit_output_parameters(
        self,
        *,
        project_id: str,
        chip_id: str,
        username: str,
        source_doc: TaskResultHistoryDocument,
        source_qid: str,
        outputs_by_qid: dict[str, dict[str, dict[str, Any]]],
        kind: str,
    ) -> str:
        """Write output parameters for each qubit, with history and provenance records.

        ``outputs_by_qid`` maps a qid to the parameter dict accepted by ``update_calib_data``.
        ``kind`` names the edit (e.g. "reanalysis") and becomes both a tag and a note key.
        """
        execution_id = f"{kind}-{uuid.uuid4().hex[:8]}"
        task_time = now()
        tags = sorted({*source_doc.tags, kind})

        # One activity per commit, mirroring manual edits and seed imports, so these values
        # appear in the lineage view instead of looking like they came from nowhere.
        activity = self._activity_repo.create_activity(
            execution_id=execution_id,
            task_id=execution_id,
            task_name=source_doc.name,
            project_id=project_id,
            task_type=kind,
            qid=source_qid,
            chip_id=chip_id,
            started_at=task_time,
            status="running",
        )
        self.link_source_parameters(
            activity_id=activity.activity_id,
            project_id=project_id,
            execution_id=execution_id,
            source_task_id=source_doc.task_id,
        )

        for qid, output_parameters in outputs_by_qid.items():
            self.ensure_qubit_qid(qid)
            self._qubit_repo.update_calib_data(
                username=username,
                qid=qid,
                chip_id=chip_id,
                output_parameters=output_parameters,
                project_id=project_id,
            )
            TaskResultHistoryDocument(
                project_id=project_id,
                username=username,
                task_id=f"{execution_id}-q{qid}",
                name=source_doc.name,
                upstream_id=source_doc.upstream_id,
                status="completed",
                message=f"{kind} by {username} from source task {source_doc.task_id}",
                input_parameters=source_doc.input_parameters,
                output_parameters=output_parameters,
                output_parameter_names=list(output_parameters),
                run_parameters=source_doc.run_parameters,
                note={
                    kind: {
                        "source_task_id": source_doc.task_id,
                        "source_qid": source_qid,
                    }
                },
                figure_path=[],
                json_figure_path=[],
                raw_data_path=[],
                start_at=task_time,
                end_at=task_time,
                elapsed_time=0.0,
                task_type=source_doc.task_type or "qubit",
                system_info=SystemInfoModel(),
                qid=qid,
                execution_id=execution_id,
                tags=tags,
                chip_id=chip_id,
                source_task_id=source_doc.task_id,
            ).insert()

            for name, parameter in output_parameters.items():
                self._record_parameter_version(
                    activity_id=activity.activity_id,
                    project_id=project_id,
                    chip_id=chip_id,
                    execution_id=execution_id,
                    task_id=f"{execution_id}-q{qid}",
                    task_name=source_doc.name,
                    qid=qid,
                    name=name,
                    parameter=parameter,
                )

        activity.ended_at = now()
        activity.status = "completed"
        activity.save()

        return execution_id

    def _record_parameter_version(
        self,
        *,
        activity_id: str,
        project_id: str,
        chip_id: str,
        execution_id: str,
        task_id: str,
        task_name: str,
        qid: str,
        name: str,
        parameter: dict[str, Any],
    ) -> None:
        """Version one parameter and attach it to the activity that produced it."""
        value = parameter.get("value")
        if isinstance(value, bool) or not isinstance(value, int | float):
            return

        param_version = self._param_version_repo.create_version(
            parameter_name=name,
            qid=qid,
            value=value,
            execution_id=execution_id,
            task_id=task_id,
            project_id=project_id,
            task_name=task_name,
            chip_id=chip_id,
            unit=str(parameter.get("unit") or ""),
            error=0.0,
            value_type="float" if isinstance(value, float) else "int",
        )
        self._relation_repo.create_relation(
            relation_type=ProvenanceRelationType.GENERATED_BY,
            source_type="entity",
            source_id=param_version.entity_id,
            target_type="activity",
            target_id=activity_id,
            project_id=project_id,
            execution_id=execution_id,
        )

    def link_source_parameters(
        self,
        *,
        activity_id: str,
        project_id: str,
        execution_id: str,
        source_task_id: str,
    ) -> None:
        """Record that this edit consumed the source experiment's parameter versions.

        Without it the lineage would start at the edit, hiding which measurement the values
        were read off. Missing source versions are not fatal: older runs may predate provenance.
        """
        for version in self._param_version_repo.get_by_task(project_id, source_task_id):
            self._relation_repo.create_relation(
                relation_type=ProvenanceRelationType.USED,
                source_type="activity",
                source_id=activity_id,
                target_type="entity",
                target_id=version.entity_id,
                project_id=project_id,
                execution_id=execution_id,
            )

    @staticmethod
    def ensure_qubit_qid(qid: str) -> None:
        """Reject coupling qids such as "4-5"; calibration writes here are qubit-only."""
        try:
            int(qid)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"qid {qid!r} is not a qubit id. Manual output-parameter updates support "
                    "qubits only."
                ),
            ) from exc

    @staticmethod
    def load_source_task_result(*, project_id: str, task_id: str) -> TaskResultHistoryDocument:
        doc = TaskResultHistoryDocument.find_one(
            {"project_id": project_id, "task_id": task_id}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail=f"Task result {task_id!r} not found.")
        return doc

    def reject_derived_parameters(
        self,
        *,
        source_doc: TaskResultHistoryDocument,
        project_id: str,
        names: set[str],
    ) -> None:
        """Refuse edits that would leave a derived parameter inconsistent.

        A derived value (e.g. readout_amplitude = f(optimal_power)) is only reproducible by the
        task that defines the relation, so neither it nor its source can be corrected here.
        """
        derived_from = self._derived_from_map(source_doc=source_doc, project_id=project_id)

        for name in sorted(names):
            source = derived_from.get(name)
            if source:
                raise HTTPException(
                    status_code=400,
                    detail=f"{name} is derived from {source}; edit {source} instead.",
                )

        sources_with_dependents = {
            source: name for name, source in derived_from.items() if source in names
        }
        if sources_with_dependents:
            source, dependent = next(iter(sources_with_dependents.items()))
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{dependent} is derived from {source}, so {source} cannot be corrected here. "
                    "Use the task's re-analysis, which recomputes both."
                ),
            )

    @staticmethod
    def _derived_from_map(
        *, source_doc: TaskResultHistoryDocument, project_id: str
    ) -> dict[str, str]:
        """Collect parameter -> source relations from the run, falling back to the task definition.

        Task results recorded before ``derived_from`` existed carry no relation, so the task
        definition is consulted as well.
        """
        derived: dict[str, str] = {}

        for parameters in (
            source_doc.output_parameters or {},
            QubitParameterService._task_output_definitions(
                project_id=project_id, name=source_doc.name
            ),
        ):
            for name, parameter in parameters.items():
                if name in derived or not isinstance(parameter, dict):
                    continue
                source = parameter.get("derived_from")
                if isinstance(source, str) and source:
                    derived[name] = source

        return derived

    @staticmethod
    def _task_output_definitions(*, project_id: str, name: str) -> dict[str, Any]:
        doc = TaskDocument.find_one({"project_id": project_id, "name": name}).run()
        return doc.output_parameters or {} if doc else {}

    @staticmethod
    def _stored_unit(parameter: Any) -> str:
        if isinstance(parameter, dict):
            unit = parameter.get("unit")
            if isinstance(unit, str):
                return unit
        return ""

    def _current_values(self, *, project_id: str, chip_id: str, qid: str) -> dict[str, float]:
        calibration_data = self._qubit_repo.get_calibration_data(
            project_id=project_id,
            chip_id=chip_id,
            qid=qid,
        )
        values: dict[str, float] = {}
        for name, parameter in calibration_data.items():
            value = parameter.get("value") if isinstance(parameter, dict) else parameter
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            numeric = float(value)
            if math.isfinite(numeric):
                values[name] = numeric
        return values
