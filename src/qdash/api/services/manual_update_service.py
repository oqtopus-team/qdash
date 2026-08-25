"""Manual parameter update service.

Allows users to manually update calibration parameters from the UI,
with provenance tracking for audit trail.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio
from bunnet import SortDirection
from fastapi import HTTPException

from qdash.api.schemas.calibration import (
    ManualEditItem,
    ManualEditsResponse,
    ManualParameterUpdateRequest,
    ManualParameterUpdateResponse,
)
from qdash.common.config.path_resolver import resolve_calib_data_path
from qdash.common.utils.datetime import now
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.provenance import ParameterVersionDocument, ProvenanceRelationType
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.coupling import MongoCouplingCalibrationRepository
from qdash.repository.filesystem import FilesystemCalibDataSaver
from qdash.repository.provenance import (
    MongoActivityRepository,
    MongoParameterVersionRepository,
    MongoProvenanceRelationRepository,
)
from qdash.repository.qubit import MongoQubitCalibrationRepository

logger = logging.getLogger(__name__)

_MANUALLY_CORRECTABLE_TASKS = {
    "CheckQubitSpectroscopy",
    "CheckResonatorSpectroscopy",
}


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
        source_doc = self._validate_source_task(request, project_id)
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

        figure_paths: list[str] = []
        json_figure_paths: list[str] = []
        task_result: TaskResultHistoryDocument | None = None
        try:
            figure_paths, json_figure_paths = self._save_correction_figure(
                source_doc=source_doc,
                request=request,
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

            if source_doc is not None:
                for source_version in self._param_version_repo.get_by_task(
                    project_id=project_id, task_id=source_doc.task_id
                ):
                    self._relation_repo.create_relation(
                        relation_type=ProvenanceRelationType.USED,
                        source_type="activity",
                        source_id=activity.activity_id,
                        target_type="entity",
                        target_id=source_version.entity_id,
                        project_id=project_id,
                        execution_id=execution_id,
                    )

            # Record in TaskResultHistory so metrics page picks up the new values.
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
                note=(
                    {"manual_correction": request.correction_point.model_dump()}
                    if request.correction_point is not None
                    else {}
                ),
                figure_path=figure_paths,
                json_figure_path=json_figure_paths,
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
                source_task_id=source_doc.task_id if source_doc is not None else None,
            )
            task_result.insert()

            activity.status = "completed"
            activity.ended_at = now()
            activity.save()

            # Apply calibration values only after every audit record has been persisted. QDash's
            # default standalone MongoDB deployment does not support multi-document transactions;
            # keeping this as the final write prevents later persistence failures from leaving an
            # untracked calibration change.
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
        except Exception:
            try:
                activity.status = "failed"
                activity.ended_at = now()
                activity.save()
                if task_result is not None:
                    task_result.status = "failed"
                    task_result.message = f"Manual parameter edit failed for {username}"
                    task_result.figure_path = []
                    task_result.json_figure_path = []
                    task_result.save()
            except Exception:
                logger.exception("Failed to persist manual correction failure state")
            finally:
                self._remove_correction_artifacts(figure_paths, json_figure_paths)
            raise

        logger.info(
            "Manual parameter update: chip=%s, qid=%s, params=%s, user=%s",
            request.chip_id,
            request.qid,
            list(request.parameters.keys()),
            username,
        )

        return ManualParameterUpdateResponse(
            updated_count=len(request.parameters),
            task_id=task_id,
            execution_id=execution_id,
            provenance_activity_id=activity.activity_id,
        )

    def _validate_source_task(
        self,
        request: ManualParameterUpdateRequest,
        project_id: str,
    ) -> TaskResultHistoryDocument | None:
        """Validate a correction against the source spectroscopy result."""
        if request.source_task_id is None:
            return None

        source_doc = TaskResultHistoryDocument.find_one(
            {"project_id": project_id, "task_id": request.source_task_id}
        ).run()
        if source_doc is None:
            raise HTTPException(status_code=404, detail="Source task result not found")
        if source_doc.name not in _MANUALLY_CORRECTABLE_TASKS:
            raise HTTPException(
                status_code=400,
                detail=f"Manual correction is not supported for {source_doc.name}",
            )
        if source_doc.chip_id != request.chip_id or source_doc.qid != request.qid:
            raise HTTPException(
                status_code=400,
                detail="Source task result does not match the requested chip and qid",
            )

        allowed_names = set(source_doc.output_parameter_names)
        unknown_names = sorted(set(request.parameters) - allowed_names)
        if unknown_names:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown source output parameter(s): {', '.join(unknown_names)}",
            )
        return source_doc

    @staticmethod
    def _save_correction_figure(
        source_doc: TaskResultHistoryDocument | None,
        request: ManualParameterUpdateRequest,
    ) -> tuple[list[str], list[str]]:
        """Persist a marker-overlay figure for later review of a manual correction."""
        if source_doc is None or request.correction_point is None:
            return [], []
        if not source_doc.json_figure_path:
            raise HTTPException(
                status_code=400,
                detail="The source task result has no Plotly figure to annotate",
            )

        source_path = resolve_calib_data_path(source_doc.json_figure_path[0])
        if not source_path.exists():
            raise HTTPException(status_code=404, detail="The source Plotly figure is missing")

        try:
            figure = pio.from_json(source_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to read the source Plotly figure: {error}",
            ) from error

        point = request.correction_point
        figure.add_trace(
            go.Scatter(
                x=[point.x],
                y=[point.y],
                mode="markers+text",
                name="Manual correction",
                text=["Manual correction"],
                textposition="top center",
                marker={"color": "red", "size": 12, "symbol": "x", "line": {"width": 2}},
                hovertemplate="x=%{x}<br>y=%{y}<extra>Manual correction</extra>",
            )
        )
        figure.add_annotation(
            x=point.x,
            y=point.y,
            text=f"Manual correction: x={point.x:.8g}, y={point.y:.8g}",
            showarrow=True,
            arrowhead=2,
            ax=35,
            ay=-35,
        )

        saver = FilesystemCalibDataSaver(str(source_path.parent.parent))
        return saver.save_figures(
            [figure],
            "ManualParameterEdit",
            "qubit",
            request.qid,
            output_dir=str(source_path.parent),
        )

    @staticmethod
    def _remove_correction_artifacts(figure_paths: list[str], json_figure_paths: list[str]) -> None:
        """Remove generated correction artifacts after a failed correction write."""
        for artifact_path in [*figure_paths, *json_figure_paths]:
            ManualUpdateService._remove_correction_artifact(artifact_path)

    @staticmethod
    def _remove_correction_artifact(artifact_path: str) -> None:
        """Remove one generated correction artifact without masking the original failure."""
        try:
            Path(artifact_path).unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to remove correction artifact %s", artifact_path)

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
