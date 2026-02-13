"""Bring-up calibration steps.

This module defines steps for initial qubit characterization:
- BringUp: Resonator and qubit spectroscopy for frequency estimation

Tasks include:
- MUX-level tasks: Executed once per MUX for representative qubit (qid % 4 == 0)
- Qubit-level tasks: Executed for each qubit individually
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger
from qdash.workflow.service.results import OneQubitResult
from qdash.workflow.service.steps.base import CalibrationStep
from qdash.workflow.service.tasks import BRINGUP_TASKS

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class BringUp(CalibrationStep):
    """Bring-up calibration step for initial qubit characterization.

    Executes BRINGUP_TASKS:
    - CheckResonatorSpectroscopy (MUX-level): Estimates resonator_frequency
    - CheckQubitSpectroscopy (Qubit-level): Estimates qubit_frequency, anharmonicity

    MUX-level tasks run once per MUX for the representative qubit (qid % 4 == 0).
    Qubit-level tasks run for each qubit individually.

    Provides: bringup

    Metrics extracted:
    - estimated_resonator_frequency (GHz): From resonator spectroscopy
    - qubit_frequency (GHz): f01 transition frequency from qubit spectroscopy
    - anharmonicity (GHz): alpha = f12 - f01 (typically negative for transmon)

    Example:
        # Basic usage
        BringUp()

        # With custom tasks
        BringUp(tasks=["CheckResonatorSpectroscopy", "CheckQubitSpectroscopy"])
    """

    mode: str = "scheduled"
    tasks: list[str] = field(default_factory=lambda: list(BRINGUP_TASKS))

    @property
    def name(self) -> str:
        return "bringup"

    @property
    def provides(self) -> set[str]:
        return {"bringup"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute MUX-level bring-up calibration.

        Note: MUX tasks are automatically skipped for non-representative qubits
        by the scheduling infrastructure.
        """
        logger = get_run_logger()
        tasks = self.tasks

        logger.info(f"[{self.name}] Starting with mode={self.mode}, {len(tasks)} tasks")

        from qdash.workflow.service.strategy import OneQubitConfig, get_one_qubit_strategy
        from qdash.workflow.service.targets import MuxTargets

        if isinstance(targets, MuxTargets):
            config = OneQubitConfig(
                mux_ids=targets.mux_ids,
                exclude_qids=targets.exclude_qids,
                tasks=tasks,
                flow_name=f"{service.flow_name}_{self.name}" if service.flow_name else self.name,
                project_id=service.project_id,
            )
            strategy = get_one_qubit_strategy(self.mode)
            raw_results = strategy.execute(service, config)
        else:
            qids = targets.to_qids(service.chip_id)
            raw_results = self._execute_direct(service, qids, tasks)

        # Build typed result
        result = self._build_result(raw_results)

        # Store in context metadata
        ctx.metadata["bringup"] = result

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
        service: CalibService,
        qids: list[str],
        tasks: list[str],
    ) -> dict[str, Any]:
        """Direct execution for QubitTargets using multiprocess parallelism."""
        from qdash.workflow.service._internal.scheduling_tasks import (
            run_qubit_calibrations_parallel,
        )

        # Build session config for multiprocess execution
        session_config = {
            "username": service.username,
            "chip_id": service.chip_id,
            "backend_name": service.backend_name,
            "execution_id": service.execution_id,
            "project_id": service.project_id,
            "default_run_parameters": service.default_run_parameters,
        }

        results = run_qubit_calibrations_parallel(
            qids=qids,
            tasks=tasks,
            session_config=session_config,
        )
        return {"direct": results}

    def _build_result(self, raw_results: dict[str, Any]) -> OneQubitResult:
        """Build typed result from raw backend data."""
        from qdash.workflow.service.results import QubitCalibData

        result = OneQubitResult()
        for stage_data in raw_results.values():
            if not isinstance(stage_data, dict):
                continue
            for qid, raw in stage_data.items():
                if not isinstance(raw, dict):
                    continue

                # Check if this was a skipped execution (MUX task for non-representative qubit)
                was_skipped = any(
                    isinstance(task_result, dict) and task_result.get("skipped", False)
                    for task_result in raw.values()
                    if isinstance(task_result, dict)
                )

                # Mark skipped qubits as success (intentional skip) with skipped flag in raw
                if was_skipped:
                    raw["_skipped"] = True

                result.add_qubit(
                    qid,
                    QubitCalibData(
                        status="success" if raw.get("status") == "success" else "failed",
                        metrics=self._extract_metrics(raw),
                        raw=raw,
                    ),
                )
        return result

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from raw result."""
        metrics: dict[str, float] = {}

        # Resonator frequency from CheckResonatorSpectroscopy
        reso_result = raw.get("CheckResonatorSpectroscopy", {})
        if reso_result and not reso_result.get("skipped", False):
            freq_param = reso_result.get("estimated_resonator_frequency")
            if freq_param is not None:
                metrics["estimated_resonator_frequency"] = (
                    freq_param.value if hasattr(freq_param, "value") else freq_param
                )

        # Qubit frequency and anharmonicity from CheckQubitSpectroscopy
        qubit_result = raw.get("CheckQubitSpectroscopy", {})
        if qubit_result and not qubit_result.get("skipped", False):
            # Qubit frequency (f01)
            qubit_freq_param = qubit_result.get("qubit_frequency")
            if qubit_freq_param is not None:
                metrics["qubit_frequency"] = (
                    qubit_freq_param.value
                    if hasattr(qubit_freq_param, "value")
                    else qubit_freq_param
                )

            # Anharmonicity (α = f12 - f01)
            anharm_param = qubit_result.get("anharmonicity")
            if anharm_param is not None:
                value = anharm_param.value if hasattr(anharm_param, "value") else anharm_param
                if value is not None:
                    metrics["anharmonicity"] = value

        return metrics
