"""Manual parameter update service.

Allows users to manually update calibration parameters from the UI,
with provenance tracking for audit trail.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from bunnet import SortDirection

from qdash.api.schemas.calibration import (
    ManualEditItem,
    ManualEditsResponse,
    ManualParameterUpdateRequest,
    ManualParameterUpdateResponse,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.provenance import ParameterVersionDocument, ProvenanceRelationType
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.coupling import MongoCouplingCalibrationRepository
from qdash.repository.provenance import (
    MongoActivityRepository,
    MongoParameterVersionRepository,
    MongoProvenanceRelationRepository,
)
from qdash.repository.qubit import MongoQubitCalibrationRepository

logger = logging.getLogger(__name__)


class ManualUpdateService:
    """Service for manually updating calibration parameters."""

    def __init__(
        self,
        qubit_repo: MongoQubitCalibrationRepository | None = None,
        coupling_repo: MongoCouplingCalibrationRepository | None = None,
        activity_repo: MongoActivityRepository | None = None,
        param_version_repo: MongoParameterVersionRepository | None = None,
        relation_repo: MongoProvenanceRelationRepository | None = None,
    ) -> None:
        self._qubit_repo = qubit_repo or MongoQubitCalibrationRepository()
        self._coupling_repo = coupling_repo or MongoCouplingCalibrationRepository()
        self._activity_repo = activity_repo or MongoActivityRepository()
        self._param_version_repo = param_version_repo or MongoParameterVersionRepository()
        self._relation_repo = relation_repo or MongoProvenanceRelationRepository()

    def update_parameters(
        self,
        request: ManualParameterUpdateRequest,
        project_id: str,
        username: str,
    ) -> ManualParameterUpdateResponse:
        """Update calibration parameters and record provenance."""
        is_coupling = "-" in request.qid
        execution_id = f"manual-edit-{uuid.uuid4().hex[:8]}"
        task_id = f"manual-edit-{uuid.uuid4().hex[:8]}"
        start_time = now()

        # Create provenance activity
        activity = self._activity_repo.create_activity(
            execution_id=execution_id,
            task_id=task_id,
            task_name="ManualParameterEdit",
            project_id=project_id,
            task_type="manual_edit",
            qid=request.qid,
            chip_id=request.chip_id,
            started_at=start_time,
            status="running",
        )

        # Build output_parameters dict for repository
        output_parameters: dict[str, Any] = {}
        for param_name, param_data in request.parameters.items():
            output_parameters[param_name] = {
                "value": param_data.get("value"),
                "unit": param_data.get("unit", ""),
                "description": param_data.get("description", f"Manually edited ({param_name})"),
            }

        # Update DB
        if is_coupling:
            self._coupling_repo.update_calib_data(
                username=username,
                qid=request.qid,
                chip_id=request.chip_id,
                output_parameters=output_parameters,
                project_id=project_id,
            )
        else:
            self._qubit_repo.update_calib_data(
                username=username,
                qid=request.qid,
                chip_id=request.chip_id,
                output_parameters=output_parameters,
                project_id=project_id,
            )

        # Record provenance for each parameter
        for param_name, param_data in request.parameters.items():
            value = param_data.get("value")
            unit = param_data.get("unit", "")
            if isinstance(value, float):
                value_type = "float"
            elif isinstance(value, int):
                value_type = "int"
            else:
                value_type = "str"
                value = str(value)

            param_version = self._param_version_repo.create_version(
                parameter_name=param_name,
                qid=request.qid,
                value=value,
                execution_id=execution_id,
                task_id=task_id,
                project_id=project_id,
                task_name="ManualParameterEdit",
                chip_id=request.chip_id,
                unit=unit,
                error=0.0,
                value_type=value_type,
            )

            self._relation_repo.create_relation(
                relation_type=ProvenanceRelationType.GENERATED_BY,
                source_type="entity",
                source_id=param_version.entity_id,
                target_type="activity",
                target_id=activity.activity_id,
                project_id=project_id,
                execution_id=execution_id,
            )

        # Record in TaskResultHistory so metrics page picks up the new values
        task_type = "coupling" if is_coupling else "qubit"
        task_result = TaskResultHistoryDocument(
            project_id=project_id,
            username=username,
            task_id=task_id,
            name="ManualParameterEdit",
            upstream_id="",
            status="completed",
            message=f"Manual parameter edit by {username}",
            input_parameters={},
            output_parameters=output_parameters,
            output_parameter_names=list(output_parameters.keys()),
            run_parameters={},
            note={},
            figure_path=[],
            json_figure_path=[],
            raw_data_path=[],
            start_at=start_time,
            end_at=start_time,
            elapsed_time=0.0,
            task_type=task_type,
            system_info=SystemInfoModel(),
            qid=request.qid,
            execution_id=execution_id,
            tags=["manual-edit"],
            chip_id=request.chip_id,
        )
        task_result.insert()

        logger.info(
            "Manual parameter update: chip=%s, qid=%s, params=%s, user=%s",
            request.chip_id,
            request.qid,
            list(request.parameters.keys()),
            username,
        )

        return ManualParameterUpdateResponse(
            updated_count=len(request.parameters),
            provenance_activity_id=activity.activity_id,
        )

    def get_manual_edits(self, project_id: str, qid: str) -> ManualEditsResponse:
        """Get all manual edits for a qid (most recent per parameter)."""
        docs = (
            ParameterVersionDocument.find(
                {
                    "project_id": project_id,
                    "qid": qid,
                    "task_name": "ManualParameterEdit",
                }
            )
            .sort([("valid_from", SortDirection.DESCENDING)])
            .limit(100)
            .run()
        )

        # Keep only the most recent edit per parameter
        seen: set[str] = set()
        edits: list[ManualEditItem] = []
        for doc in docs:
            if doc.parameter_name in seen:
                continue
            seen.add(doc.parameter_name)
            edits.append(
                ManualEditItem(
                    parameter_name=doc.parameter_name,
                    value=doc.value,
                    unit=doc.unit,
                    edited_at=doc.valid_from,
                    execution_id=doc.execution_id,
                )
            )

        return ManualEditsResponse(qid=qid, edits=edits)
