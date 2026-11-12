"""Bring-up calibration steps.

This module defines steps for initial qubit characterization:
- BringUp: Resonator and qubit spectroscopy for frequency estimation

Tasks include:
- MUX-level tasks: Executed once per MUX for representative qubit (qid % 4 == 0)
- Qubit-level tasks: Executed for each qubit individually
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from prefect import get_run_logger

from qdash.datamodel.calibration_pipeline import BRINGUP_METRICS
from qdash.datamodel.task_call import StepCalls, TaskCall, normalize_calls
from qdash.workflow.service._internal.call_runner import (
    NOT_MUX_REPRESENTATIVE,
    call_results,
    latest_call_output,
)
from qdash.workflow.service.results import (
    OneQubitResult,
    build_one_qubit_result,
    normalize_metric_value,
)
from qdash.workflow.service.steps.base import CalibrationStep, OneQubitExecutionModeMixin
from qdash.workflow.service.tasks import BRINGUP_TASKS

if TYPE_CHECKING:
    from qdash.workflow.service._internal.session import CalibSession
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class BringUp(OneQubitExecutionModeMixin, CalibrationStep):
    """Bring-up calibration step for initial qubit characterization.

    Executes BRINGUP_TASKS:
    - CheckResonatorSpectroscopy (MUX-level): Estimates readout_frequency
    - CheckQubitSpectroscopy: Estimates coarse_qubit_frequency and coarse_control_amplitude
    - CheckControlAmplitude: Refines coarse_control_amplitude via sqrt-Lorentzian fit
    - CheckAdaptiveChevron: Adaptive rough/fine search for qubit_frequency
    - CheckRabi: Refines control_amplitude (Rabi-rate-derived)

    Hardware reconfiguration is intentionally kept outside bring-up so intermediate
    task outputs are passed through QDash state without reloading backend params
    between tasks.

    MUX-level tasks run once per MUX for the representative qubit (qid % 4 == 0).
    Qubit-level tasks run for each qubit individually.

    ``execution_mode`` applies to MUX targets and defaults to ``parallel_by_mux``;
    explicit qubit targets run directly in parallel. The deprecated ``mode``
    argument and old mode names are still accepted with a ``DeprecationWarning``
    (see :mod:`qdash.datamodel.one_qubit_execution_mode`).

    Provides: bringup

    Metrics extracted:
    - readout_frequency (GHz): From resonator spectroscopy
    - readout_amplitude (a.u.): From resonator spectroscopy optimal power
    - coarse_qubit_frequency (GHz): f01 estimate from qubit spectroscopy
    - qubit_frequency (GHz): Refined f01 transition frequency from adaptive Chevron

    Example:
        # Basic usage
        BringUp()

        # With custom tasks
        BringUp(tasks=[
            TaskCall(name="CheckResonatorSpectroscopy"),
            TaskCall(name="CheckQubitSpectroscopy"),
        ])
    """

    execution_mode: str | None = None
    tasks: list[TaskCall] = field(default_factory=lambda: list(BRINGUP_TASKS))
    resonator_assignment_order: list[int] | None = None
    mode: str | None = None  # Deprecated alias of execution_mode

    step_metrics: ClassVar[tuple[str, ...]] = BRINGUP_METRICS

    def __post_init__(self) -> None:
        self._resolve_execution_mode("parallel_by_mux")
        self.tasks = list(normalize_calls(self.tasks, where=f"{self.name}.tasks"))

    @property
    def name(self) -> str:
        return self.step_id or "bringup"

    def calls(self) -> tuple[TaskCall, ...]:
        """The calls, with ``resonator_assignment_order`` on resonator spectroscopy.

        A call's own ``run`` value for the order takes precedence.
        """
        if self.resonator_assignment_order is None:
            return tuple(self.tasks)
        order = list(self.resonator_assignment_order)
        return tuple(
            TaskCall.model_validate(
                {
                    **call.model_dump(),
                    "run": {"resonator_assignment_order": order, **(call.run or {})},
                }
            )
            if call.name == "CheckResonatorSpectroscopy"
            and "resonator_assignment_order" not in (call.run or {})
            else call
            for call in self.tasks
        )

    @property
    def provides(self) -> set[str]:
        return {"bringup"}

    def execute(
        self,
        session: CalibSession,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute MUX-level bring-up calibration.

        Note: MUX tasks are automatically skipped for non-representative qubits
        by the scheduling infrastructure.
        """
        logger = get_run_logger()
        plan = self.step_calls(session)

        self._log_execution_mode_deprecations(logger)
        logger.info(
            f"[{self.name}] Starting with execution_mode={self.execution_mode}, "
            f"{len(plan.calls)} calls"
        )

        from qdash.workflow.service.strategy import OneQubitConfig, get_one_qubit_strategy
        from qdash.workflow.service.targets import MuxTargets

        if isinstance(targets, MuxTargets):
            config = OneQubitConfig(
                mux_ids=targets.mux_ids,
                exclude_qids=targets.exclude_qids,
                plan=plan,
            )
            strategy = get_one_qubit_strategy(self.resolved_execution_mode)
            raw_results = strategy.execute(session, config)
        else:
            qids = targets.to_qids(session.chip_id)
            raw_results = self._execute_direct(session, qids, plan)

        # Build typed result
        result = self._build_result(raw_results)

        # Store in context metadata
        ctx.metadata["bringup"] = result
        ctx.record_step_result(self.resolved_step_id, result)

        # Count actual executions (exclude skipped)
        executed_count = sum(
            1
            for qid, data in result.qubits.items()
            if data.status == "success" and not data.raw.get("_skipped", False)
        )
        total_muxes = len(targets.mux_ids) if isinstance(targets, MuxTargets) else 0

        logger.info(
            f"[{self.name}] Completed. "
            f"{executed_count} MUX(es) processed"
            + (f" (out of {total_muxes} MUXes)" if total_muxes else "")
        )
        return ctx

    def _execute_direct(
        self,
        session: CalibSession,
        qids: list[str],
        plan: StepCalls | None = None,
    ) -> dict[str, Any]:
        """Direct execution for QubitTargets using multiprocess parallelism."""
        from qdash.workflow.service._internal.scheduling_tasks import (
            run_qubit_calibrations_parallel,
        )

        results = run_qubit_calibrations_parallel(
            qids=qids,
            plan=plan or self.step_calls(session),
            worker=session.worker_spec(),
        )
        return {"direct": results}

    def _build_result(self, raw_results: dict[str, Any]) -> OneQubitResult:
        """Build typed result from raw backend data."""
        for stage_data in raw_results.values():
            if not isinstance(stage_data, dict):
                continue
            for raw in stage_data.values():
                # A qubit that skipped a MUX task (not the MUX representative) is
                # marked so the summary does not count it as a processed MUX.
                if isinstance(raw, dict) and any(
                    call.get("reason") == NOT_MUX_REPRESENTATIVE for call in call_results(raw)
                ):
                    raw["_skipped"] = True
        return build_one_qubit_result(raw_results, self.resolved_step_id, self._extract_metrics)

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from the latest call of each task in the step."""
        metrics: dict[str, float] = {}

        # Readout parameters from CheckResonatorSpectroscopy
        reso_result = latest_call_output(raw, "CheckResonatorSpectroscopy")
        freq_param = reso_result.get("readout_frequency") or reso_result.get(
            "estimated_resonator_frequency"
        )
        if (value := normalize_metric_value(freq_param)) is not None:
            metrics["readout_frequency"] = value
        if (value := normalize_metric_value(reso_result.get("readout_amplitude"))) is not None:
            metrics["readout_amplitude"] = value

        # Coarse qubit frequency (f01) from CheckQubitSpectroscopy. The proper
        # qubit_frequency comes from CheckAdaptiveChevron's adaptive chevron fit.
        qubit_result = latest_call_output(raw, "CheckQubitSpectroscopy")
        coarse = normalize_metric_value(qubit_result.get("coarse_qubit_frequency"))
        if coarse is not None:
            metrics["coarse_qubit_frequency"] = coarse

        chevron_result = latest_call_output(raw, "CheckAdaptiveChevron")
        if (value := normalize_metric_value(chevron_result.get("qubit_frequency"))) is not None:
            metrics["qubit_frequency"] = value

        return metrics
