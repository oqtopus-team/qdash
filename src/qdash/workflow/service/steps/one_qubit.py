"""1-Qubit calibration steps.

This module defines steps for 1-qubit calibration:
- CustomOneQubit: Flexible custom task execution
- OneQubitCheck: Basic characterization (T1, T2, etc.)
- OneQubitFineTune: Advanced calibration (DRAG, RB, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.workflow.service.results import OneQubitResult
from qdash.workflow.service.steps.base import CalibrationStep
from qdash.workflow.service.tasks import CHECK_1Q_TASKS, FULL_1Q_TASKS_AFTER_CHECK

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService
    from qdash.workflow.service.steps.context import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class CustomOneQubit(CalibrationStep):
    """Custom 1-qubit calibration step with user-defined tasks.

    This is the most flexible 1-qubit step - you specify exactly which
    tasks to run. Use this when the predefined steps don't fit your needs.

    Example:
        # Run specific tasks
        CustomOneQubit(
            step_name="frequency_check",
            tasks=["CheckQubitSpectroscopy", "CheckFrequency"],
        )

        # Run T1/T2 characterization only
        CustomOneQubit(
            step_name="coherence_check",
            tasks=["CheckT1", "CheckT2Echo", "CheckRamsey"],
        )
    """

    step_name: str = "custom_one_qubit"
    tasks: list[str] = field(default_factory=list)
    mode: str = "synchronized"

    @property
    def name(self) -> str:
        return self.step_name

    @property
    def provides(self) -> set[str]:
        return {self.step_name, "candidate_qids"}

    def execute(
        self,
        service: "CalibService",
        targets: "Target",
        ctx: "StepContext",
    ) -> "StepContext":
        """Execute custom 1-qubit calibration."""
        logger = get_run_logger()

        if not self.tasks:
            logger.warning(f"[{self.name}] No tasks specified, skipping")
            return ctx

        logger.info(f"[{self.name}] Starting with {len(self.tasks)} tasks: {self.tasks}")

        from qdash.workflow.service.strategy import OneQubitConfig, get_one_qubit_strategy
        from qdash.workflow.service.targets import MuxTargets

        if isinstance(targets, MuxTargets):
            config = OneQubitConfig(
                mux_ids=targets.mux_ids,
                exclude_qids=targets.exclude_qids,
                tasks=self.tasks,
                flow_name=f"{service.flow_name}_{self.name}" if service.flow_name else self.name,
                project_id=service.project_id,
            )
            strategy = get_one_qubit_strategy(self.mode)
            raw_results = strategy.execute(service, config)
        else:
            qids = targets.to_qids(service.chip_id)
            raw_results = self._execute_direct(service, qids)

        # Build typed result
        result = self._build_result(raw_results)

        # Store in metadata with step name as key
        ctx.metadata[self.step_name] = result

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_qids())}/{len(result.qubits)} successful"
        )
        return ctx

    def _execute_direct(
        self,
        service: "CalibService",
        qids: list[str],
    ) -> dict[str, Any]:
        """Direct execution for QubitTargets."""
        from qdash.workflow.service._internal.prefect_tasks import calibrate_single_qubit

        results = {}
        futures = [calibrate_single_qubit.submit(qid, self.tasks) for qid in qids]
        for future in futures:
            qid, result = future.result()
            results[qid] = result
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
        """Extract metrics from raw result.

        Custom steps don't auto-extract metrics - raw data is available via result.raw.
        Users can subclass and override this for specific metric extraction.
        """
        return {}


@dataclass
class OneQubitCheck(CalibrationStep):
    """Basic 1-qubit characterization step.

    Executes CHECK_1Q_TASKS: CheckRabi, CreateHPIPulse, CheckHPIPulse,
    CheckT1, CheckT2Echo, CheckRamsey.

    Provides: one_qubit_check
    """

    mode: str = "synchronized"
    tasks: list[str] | None = None

    @property
    def name(self) -> str:
        return "one_qubit_check"

    @property
    def provides(self) -> set[str]:
        return {"one_qubit_check", "candidate_qids"}

    def execute(
        self,
        service: "CalibService",
        targets: "Target",
        ctx: "StepContext",
    ) -> "StepContext":
        """Execute 1-qubit check calibration."""
        logger = get_run_logger()
        tasks = self.tasks or CHECK_1Q_TASKS

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
        ctx.one_qubit_check = result

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_qids())}/{len(result.qubits)} successful"
        )
        return ctx

    def _execute_direct(
        self,
        service: "CalibService",
        qids: list[str],
        tasks: list[str],
    ) -> dict[str, Any]:
        """Direct execution for QubitTargets."""
        from qdash.workflow.service._internal.prefect_tasks import calibrate_single_qubit

        results = {}
        futures = [calibrate_single_qubit.submit(qid, tasks) for qid in qids]
        for future in futures:
            qid, result = future.result()
            results[qid] = result
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
        metrics = {}
        # T1
        t1_result = raw.get("CheckT1", {})
        if t1_result:
            t1_param = t1_result.get("t1")
            if t1_param is not None:
                metrics["t1"] = t1_param.value if hasattr(t1_param, "value") else t1_param
        # T2 echo
        t2_result = raw.get("CheckT2Echo", {})
        if t2_result:
            t2_param = t2_result.get("t2_echo")
            if t2_param is not None:
                metrics["t2_echo"] = t2_param.value if hasattr(t2_param, "value") else t2_param
        return metrics


@dataclass
class OneQubitFineTune(CalibrationStep):
    """Advanced 1-qubit calibration step.

    Executes FULL_1Q_TASKS_AFTER_CHECK: DRAG pulses, ReadoutClassification,
    RandomizedBenchmarking, X90InterleavedRandomizedBenchmarking.

    Requires: candidate_qids (optional, uses targets if not available)
    Provides: one_qubit_fine_tune
    """

    mode: str = "synchronized"
    tasks: list[str] | None = None

    @property
    def name(self) -> str:
        return "one_qubit_fine_tune"

    @property
    def provides(self) -> set[str]:
        return {"one_qubit_fine_tune", "candidate_qids"}

    def execute(
        self,
        service: "CalibService",
        targets: "Target",
        ctx: "StepContext",
    ) -> "StepContext":
        """Execute 1-qubit fine-tuning calibration."""
        logger = get_run_logger()
        tasks = self.tasks or FULL_1Q_TASKS_AFTER_CHECK

        # Use filtered candidates from context if available
        qids = ctx.candidate_qids if ctx.candidate_qids else targets.to_qids(service.chip_id)

        logger.info(
            f"[{self.name}] Starting with mode={self.mode}, "
            f"{len(tasks)} tasks, {len(qids)} qubits"
        )

        if not qids:
            logger.warning(f"[{self.name}] No candidate qubits, skipping")
            ctx.one_qubit_fine_tune = OneQubitResult()
            return ctx

        raw_results = self._execute_with_qids(service, qids, tasks)

        result = self._build_result(raw_results)
        ctx.one_qubit_fine_tune = result

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_qids())}/{len(result.qubits)} successful"
        )
        return ctx

    def _execute_with_qids(
        self,
        service: "CalibService",
        qids: list[str],
        tasks: list[str],
    ) -> dict[str, Any]:
        """Execute calibration for specific qubit IDs."""
        from qdash.workflow.service.strategy import OneQubitConfig, get_one_qubit_strategy

        # Convert qids to mux_ids for strategy
        mux_ids = sorted(set(int(qid) // 4 for qid in qids))
        exclude_qids: list[str] = []

        config = OneQubitConfig(
            mux_ids=mux_ids,
            exclude_qids=exclude_qids,
            qids=qids,
            tasks=tasks,
            flow_name=f"{service.flow_name}_{self.name}" if service.flow_name else self.name,
            project_id=service.project_id,
        )
        strategy = get_one_qubit_strategy(self.mode)
        result: dict[str, Any] = strategy.execute(service, config)
        return result

    def _execute_direct(
        self,
        service: "CalibService",
        qids: list[str],
        tasks: list[str],
    ) -> dict[str, Any]:
        """Direct execution for QubitTargets."""
        from qdash.workflow.service._internal.prefect_tasks import calibrate_single_qubit

        results = {}
        futures = [calibrate_single_qubit.submit(qid, tasks) for qid in qids]
        for future in futures:
            qid, result = future.result()
            results[qid] = result
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
        metrics = {}
        # X90 fidelity from IRB
        irb = raw.get("X90InterleavedRandomizedBenchmarking", {})
        if irb:
            fidelity_param = irb.get("x90_gate_fidelity")
            if fidelity_param is not None:
                metrics["x90_fidelity"] = (
                    fidelity_param.value if hasattr(fidelity_param, "value") else fidelity_param
                )
        # RB fidelity
        rb = raw.get("RandomizedBenchmarking", {})
        if rb:
            fidelity_param = rb.get("fidelity")
            if fidelity_param is not None:
                metrics["rb_fidelity"] = (
                    fidelity_param.value if hasattr(fidelity_param, "value") else fidelity_param
                )
        return metrics
