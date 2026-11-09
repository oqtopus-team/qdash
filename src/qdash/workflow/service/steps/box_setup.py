"""Box setup steps for calibration pipelines."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prefect import get_run_logger

from qdash.datamodel.calibration_pipeline import configure_all_call
from qdash.datamodel.task_settings import merge_task_parameters, normalize_task_settings
from qdash.workflow.service.steps.base import CalibrationStep
from qdash.workflow.service.targets import MuxTargets

if TYPE_CHECKING:
    from qdash.datamodel.task_call import TaskCall
    from qdash.workflow.service.calib_service import CalibService
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class ConfigureAll(CalibrationStep):
    """Configure all boxes for the selected MUXes once as a pipeline step.

    ``call`` sets the ConfigureAll call's own settings, for example
    ``TaskCall(name="ConfigureAll", run={"configuration_mode": "ge-ef-cr"})``.
    ``mux_ids`` always comes from the step or its targets.
    """

    mux_ids: list[int] | None = None
    call: TaskCall | None = None

    def __post_init__(self) -> None:
        """Reject a call that does not name the ConfigureAll task."""
        configure_all_call(self.call)

    @property
    def name(self) -> str:
        return self.step_id or "configure_all"

    def calls(self) -> tuple[TaskCall, ...]:
        """The one ConfigureAll call; ``execute`` sets its mux_ids from the targets."""
        return (configure_all_call(self.call),)

    @property
    def provides(self) -> set[str]:
        return {"configure_all"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        logger = get_run_logger()
        mux_ids = self._resolve_mux_ids(service, targets)

        logger.info(f"[{self.name}] Configuring boxes for {len(mux_ids)} MUXes")
        owns_session = not service._initialized
        if owns_session:
            service._initialize([])

        plan = self.step_calls(service)
        call = plan.calls[0]
        parameters = merge_task_parameters(
            {call.name: call.settings()},
            {call.name: normalize_task_settings(call.name, {"run": {"mux_ids": mux_ids}})},
        )[call.name]
        try:
            raw_result = service.execute_task(
                "ConfigureAll",
                qid="",
                parameters=parameters,
                invocation=plan.invocation(call),
            )
            ctx.metadata[self.name] = raw_result
            if owns_session:
                service.finish_calibration()
        except BaseException as e:
            from qdash.workflow.service.calib_service import (
                _is_cancellation,
                _is_external_termination,
            )

            if owns_session:
                if _is_cancellation(e):
                    logger.info(f"[{self.name}] Cancelled")
                    with contextlib.suppress(Exception):
                        service.cancel_calibration()
                elif _is_external_termination(e):
                    logger.info(f"[{self.name}] Interrupted by a termination signal")
                    with contextlib.suppress(Exception):
                        service.abandon_calibration()
                else:
                    logger.error(f"[{self.name}] Failed: {e}")
                    with contextlib.suppress(Exception):
                        service.fail_calibration(str(e))
            raise

        logger.info(f"[{self.name}] Completed")
        return ctx

    def _resolve_mux_ids(self, service: CalibService, targets: Target) -> list[int]:
        """The MUXes to configure: the step's own, the targets', or the session's."""
        if self.mux_ids is not None:
            return list(self.mux_ids)
        if isinstance(targets, MuxTargets):
            return list(targets.mux_ids)
        if service.muxes is not None:
            return list(service.muxes)
        qids = targets.to_qids(service.chip_id)
        return sorted({int(qid) // 4 for qid in qids})
