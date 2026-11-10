"""Box setup steps for calibration pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from prefect import get_run_logger

from qdash.datamodel.calibration_pipeline import configure_all_call
from qdash.datamodel.task_settings import merge_task_parameters, normalize_task_settings
from qdash.workflow.service.steps.base import CalibrationStep
from qdash.workflow.service.targets import MuxTargets

if TYPE_CHECKING:
    from qdash.datamodel.task_call import TaskCall
    from qdash.workflow.service._internal.session import CalibSession
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
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        logger = get_run_logger()
        mux_ids = self._resolve_mux_ids(session, targets)

        logger.info(f"[{self.name}] Configuring boxes for {len(mux_ids)} MUXes")
        # The pipeline opened this step's Execution and closes it however it ends.
        plan = self.step_calls(session)
        call = plan.calls[0]
        parameters = merge_task_parameters(
            {call.name: call.settings()},
            {call.name: normalize_task_settings(call.name, {"run": {"mux_ids": mux_ids}})},
        )[call.name]
        ctx.metadata[self.name] = session.execute_task(
            "ConfigureAll",
            qid="",
            parameters=parameters,
            invocation=plan.invocation(call),
        )

        logger.info(f"[{self.name}] Completed")
        return ctx

    def _resolve_mux_ids(self, session: CalibSession, targets: Target) -> list[int]:
        """The MUXes to configure: the step's own, or the targets'."""
        if self.mux_ids is not None:
            return list(self.mux_ids)
        if isinstance(targets, MuxTargets):
            return list(targets.mux_ids)
        qids = targets.to_qids(session.chip_id)
        return sorted({int(qid) // 4 for qid in qids})
