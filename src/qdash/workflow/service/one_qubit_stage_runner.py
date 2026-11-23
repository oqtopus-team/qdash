"""Execution helpers for one-qubit schedules within an existing session."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.workflow.service._internal.call_runner import (
    batch_preflight_problems,
    run_batch_calls,
)
from qdash.workflow.service._internal.scheduling_tasks import (
    run_mux_calibrations_parallel,
    run_qubit_batch_calibration_isolated,
)
from qdash.workflow.service.session_context import get_session

if TYPE_CHECKING:
    from qdash.datamodel.task_call import StepCalls
    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service._internal.settings import WorkerSpec


def batch_capable_tasks(backend_name: str) -> dict[str, bool]:
    """Task name -> whether the task implements ``batch_run`` on this backend."""
    from qdash.workflow.calibtasks.base import BaseTask
    from qdash.workflow.calibtasks.fake.base import FakeTask
    from qdash.workflow.calibtasks.qubex.base import QubexTask

    # These implementations declare the interface but cannot execute a batch.
    # Compare methods so inherited stubs are rejected regardless of class names.
    unsupported = {BaseTask.batch_run, QubexTask.batch_run, FakeTask.batch_run}
    return {
        name: task_class.batch_run not in unsupported
        for name, task_class in BaseTask.registry.get(backend_name, {}).items()
    }


class OneQubitStageRunner:
    """Run one-qubit schedules without owning the execution lifecycle."""

    def __init__(self, session: CalibSession) -> None:
        self.session = session

    def collect_mux_group_qids(
        self, schedule: Any, allowed_qids: list[str] | None = None
    ) -> list[str]:
        """Collect qids from the MUX groups of a ``OneQubitScheduleResult``."""
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

    def preflight_batch(self, plan: StepCalls) -> None:
        """Raise before any hardware work when the batch path cannot run ``plan``."""
        problems = batch_preflight_problems(
            plan,
            self.session.task_parameters,
            batch_capable_tasks(self.session.backend_name),
        )
        if problems:
            raise ValueError(
                "simultaneous_spectroscopy cannot run this step: " + "; ".join(problems)
            )

    def execute_parallel_by_mux_schedule(
        self,
        schedule: Any,
        *,
        plan: StepCalls,
        worker: WorkerSpec,
        allowed_qids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run a ``parallel_by_mux`` schedule under the current parent execution.

        The MUX groups of a stage run in parallel; stages run one after another.
        """
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
                    plan=plan,
                    worker=worker,
                )
                stage_results.update(mux_results)
            if stage_results:
                all_results[f"Box_{box_type}"] = stage_results
        return all_results

    def execute_simultaneous_spectroscopy_schedule(
        self,
        schedule: Any,
        *,
        plan: StepCalls,
        allowed_qids: list[str] | None = None,
        worker: WorkerSpec | None = None,
    ) -> dict[str, Any]:
        """Run simultaneous spectroscopy batches under the current execution.

        Every call runs once per schedule step over that step's qubits, so each
        call is a barrier for its batch; schedule steps run one after another.
        """
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
            if worker is not None:
                all_results[f"step_{step.step_index}"] = run_qubit_batch_calibration_isolated(
                    qids=step_qids,
                    plan=plan,
                    worker=worker,
                )
                continue
            all_results[f"step_{step.step_index}"] = run_batch_calls(
                get_session(), step_qids, plan, logger
            )
        return all_results

    @staticmethod
    def _filter_qids(qids: list[str], allowed_qids: list[str] | None) -> list[str]:
        if allowed_qids is None:
            return qids
        allowed_set = set(allowed_qids)
        return [qid for qid in qids if qid in allowed_set]
