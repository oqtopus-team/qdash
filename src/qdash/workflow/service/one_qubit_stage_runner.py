"""Execution helpers for one-qubit schedules within an existing session."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.workflow.service._internal.scheduling_tasks import run_mux_calibrations_parallel
from qdash.workflow.service.calib_service import get_session

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


class OneQubitStageRunner:
    """Run one-qubit schedules without owning the execution lifecycle."""

    def __init__(self, cal_service: CalibService, *, project_id: str | None = None) -> None:
        self.cal_service = cal_service
        self.project_id = project_id or cal_service.project_id

    def build_session_config(self, *, execution_id: str, flow_name: str | None) -> dict[str, Any]:
        """Build isolated-worker session config for the current parent execution."""
        return {
            "username": self.cal_service.username,
            "chip_id": self.cal_service.chip_id,
            "backend_name": self.cal_service.backend_name,
            "project_id": self.project_id,
            "muxes": None,
            "execution_id": execution_id,
            "default_run_parameters": self.cal_service.default_run_parameters,
            "tags": self.cal_service.tags,
            "flow_name": flow_name,
            "note": self.cal_service.note,
        }

    def collect_scheduled_qids(self, schedule: Any, allowed_qids: list[str] | None = None) -> list[str]:
        """Collect qids from a scheduled MUX plan."""
        qids: list[str] = []
        for stage_info in schedule.stages:
            for group in stage_info.parallel_groups:
                qids.extend(self._filter_qids(group, allowed_qids))
        return list(dict.fromkeys(qids))

    def collect_simultaneous_qids(
        self, schedule: Any, allowed_qids: list[str] | None = None
    ) -> list[str]:
        """Collect qids from a simultaneous spectroscopy plan."""
        qids: list[str] = []
        for step in schedule.steps:
            qids.extend(self._filter_qids(step.parallel_qids, allowed_qids))
        return list(dict.fromkeys(qids))

    def execute_scheduled_mux_schedule(
        self,
        schedule: Any,
        *,
        tasks: list[str],
        session_config: dict[str, Any],
        allowed_qids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run a scheduled MUX plan under the current parent execution."""
        stages_by_box: dict[str, list[Any]] = {}
        for stage_info in schedule.stages:
            stages_by_box.setdefault(stage_info.box_type, []).append(stage_info)

        all_results: dict[str, Any] = {}
        for box_type, stages in stages_by_box.items():
            stage_results: dict[str, Any] = {}
            for stage_info in stages:
                parallel_groups = [
                    self._filter_qids(group, allowed_qids) for group in stage_info.parallel_groups
                ]
                parallel_groups = [group for group in parallel_groups if group]
                if not parallel_groups:
                    continue
                mux_results = run_mux_calibrations_parallel(
                    mux_groups=parallel_groups,
                    tasks=tasks,
                    session_config=session_config,
                )
                stage_results.update(mux_results)
            if stage_results:
                all_results[f"Box_{box_type}"] = stage_results
        return all_results

    def execute_simultaneous_spectroscopy_schedule(
        self,
        schedule: Any,
        *,
        tasks: list[str],
        allowed_qids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run simultaneous spectroscopy batches under the current execution."""
        logger = get_run_logger()
        all_results: dict[str, Any] = {}
        for step in schedule.steps:
            step_qids = self._filter_qids(step.parallel_qids, allowed_qids)
            if not step_qids:
                continue
            logger.info(
                "Running simultaneous spectroscopy step %s with %s qids",
                step.step_index,
                len(step_qids),
            )
            session = get_session()
            step_results: dict[str, dict[str, Any]] = {qid: {} for qid in step_qids}
            for task_name in tasks:
                task_results = session.execute_task_batch(task_name, step_qids)
                for qid, task_result in task_results.items():
                    step_results.setdefault(qid, {})[task_name] = task_result
            all_results[f"step_{step.step_index}"] = step_results
        return all_results

    @staticmethod
    def _filter_qids(qids: list[str], allowed_qids: list[str] | None) -> list[str]:
        if allowed_qids is None:
            return qids
        allowed_set = set(allowed_qids)
        return [qid for qid in qids if qid in allowed_set]
