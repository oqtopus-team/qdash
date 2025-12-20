"""2-Qubit calibration and system steps.

This module defines steps for 2-qubit calibration and system-level tasks:
- CustomTwoQubit: Flexible custom 2Q task execution
- GenerateCRSchedule: CR schedule generation
- TwoQubitCalibration: Full 2Q calibration
- CheckSkew: System-level skew check
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
from qdash.workflow.service.results import SkewCheckResult, TwoQubitResult
from qdash.workflow.service.steps.base import CalibrationStep, TransformStep
from qdash.workflow.service.tasks import FULL_2Q_TASKS

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class CustomTwoQubit(CalibrationStep):
    """Custom 2-qubit calibration step with user-defined tasks.

    Similar to CustomOneQubit, this allows specifying exactly which
    2-qubit tasks to run.

    Example:
        # Run only CR check
        CustomTwoQubit(
            step_name="cr_check",
            tasks=["CheckCrossResonance"],
        )

        # Run ZX90 calibration only
        CustomTwoQubit(
            step_name="zx90_tune",
            tasks=["CreateZX90", "CheckZX90"],
        )
    """

    step_name: str = "custom_two_qubit"
    tasks: list[str] = field(default_factory=list)
    max_parallel_ops: int = 10

    @property
    def name(self) -> str:
        return self.step_name

    @property
    def requires(self) -> set[str]:
        return {"candidate_qids"}

    @property
    def provides(self) -> set[str]:
        return {self.step_name, "candidate_couplings"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute custom 2-qubit calibration."""
        logger = get_run_logger()

        if not self.tasks:
            logger.warning(f"[{self.name}] No tasks specified, skipping")
            return ctx

        candidate_qubits = ctx.candidate_qids
        if len(candidate_qubits) < 2:
            logger.warning(f"[{self.name}] Not enough candidates ({len(candidate_qubits)}) for 2Q")
            ctx.metadata[self.step_name] = TwoQubitResult()
            return ctx

        logger.info(f"[{self.name}] Starting with {len(self.tasks)} tasks: {self.tasks}")

        # Use pre-generated schedule if available, otherwise generate
        if "cr_schedule" in ctx.metadata:
            parallel_groups = ctx.metadata["cr_schedule"]
            logger.info(f"[{self.name}] Using pre-generated CR schedule")
        else:
            from qdash.workflow.engine import CRScheduler

            wiring_config_path = str(get_qubex_paths().wiring_yaml(service.chip_id))
            scheduler = CRScheduler(
                service.username,
                service.chip_id,
                wiring_config_path=wiring_config_path,
            )
            schedule = scheduler.generate(
                candidate_qubits=candidate_qubits,
                max_parallel_ops=self.max_parallel_ops,
            )
            parallel_groups = schedule.parallel_groups

        if not parallel_groups:
            logger.warning(f"[{self.name}] No valid CR pairs found")
            ctx.metadata[self.step_name] = TwoQubitResult()
            return ctx

        coupling_groups = [[f"{c}-{t}" for c, t in group] for group in parallel_groups]
        total_pairs = sum(len(g) for g in coupling_groups)
        logger.info(
            f"[{self.name}] Executing {total_pairs} coupling pairs in "
            f"{len(coupling_groups)} groups"
        )

        # Execute
        from qdash.workflow.service._internal.scheduling_tasks import calibrate_parallel_group
        from qdash.workflow.service.calib_service import (
            finish_calibration,
            get_session,
            init_calibration,
        )
        from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig

        init_calibration(
            service.username,
            service.chip_id,
            candidate_qubits,
            flow_name=f"{service.flow_name}_{self.name}" if service.flow_name else self.name,
            project_id=service.project_id,
            enable_github_pull=False,
            github_push_config=GitHubPushConfig(
                enabled=True,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
            ),
            note={
                "type": "2-qubit",
                "step_name": self.step_name,
                "tasks": self.tasks,
                "candidate_qubits": candidate_qubits,
                "schedule": coupling_groups,
            },
        )

        all_raw_results: dict[str, Any] = {}
        for group in coupling_groups:
            group_results = calibrate_parallel_group(coupling_qids=group, tasks=self.tasks)
            all_raw_results.update(group_results)

        session = get_session()
        session.record_stage_result(self.name, all_raw_results)
        finish_calibration()

        # Build typed result
        result = self._build_result(all_raw_results)
        ctx.metadata[self.step_name] = result

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_couplings())}/{total_pairs} successful"
        )
        return ctx

    def _build_result(self, raw_results: dict[str, Any]) -> TwoQubitResult:
        """Build typed result from raw backend data."""
        from qdash.workflow.service.results import CouplingCalibData

        result = TwoQubitResult()
        for coupling_id, raw in raw_results.items():
            if isinstance(raw, dict):
                result.add_coupling(
                    coupling_id,
                    CouplingCalibData(
                        status="success" if raw.get("status") == "success" else "failed",
                        metrics=self._extract_metrics(raw),
                        raw=raw,
                    ),
                )
        return result

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from raw result."""
        return {}


@dataclass
class GenerateCRSchedule(TransformStep):
    """Generate CR (Cross-Resonance) schedule for 2-qubit calibration.

    Uses CRScheduler to generate parallel execution groups based on:
    - MUX conflicts
    - Frequency constraints
    - Candidate qubit availability

    Requires: candidate_qids (at least 2 qubits)
    Provides: candidate_couplings (scheduled coupling pairs)
    """

    max_parallel_ops: int = 10

    @property
    def name(self) -> str:
        return "generate_cr_schedule"

    @property
    def requires(self) -> set[str]:
        return {"candidate_qids"}

    @property
    def provides(self) -> set[str]:
        return {"candidate_couplings"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Generate CR schedule from candidate qubits."""
        logger = get_run_logger()

        candidate_qubits = ctx.candidate_qids
        if len(candidate_qubits) < 2:
            logger.warning(f"[{self.name}] Not enough candidates ({len(candidate_qubits)}) for 2Q")
            ctx.candidate_couplings = []
            return ctx

        from qdash.workflow.engine import CRScheduler

        wiring_config_path = str(get_qubex_paths().wiring_yaml(service.chip_id))
        scheduler = CRScheduler(
            service.username,
            service.chip_id,
            wiring_config_path=wiring_config_path,
        )
        schedule = scheduler.generate(
            candidate_qubits=candidate_qubits,
            max_parallel_ops=self.max_parallel_ops,
        )

        if not schedule.parallel_groups:
            logger.warning(f"[{self.name}] No valid CR pairs found")
            ctx.candidate_couplings = []
            return ctx

        # Flatten to coupling IDs
        all_couplings = [f"{c}-{t}" for group in schedule.parallel_groups for c, t in group]
        ctx.candidate_couplings = all_couplings

        # Store schedule in metadata for TwoQubitCalibration
        ctx.metadata["cr_schedule"] = schedule.parallel_groups

        logger.info(
            f"[{self.name}] Generated {len(all_couplings)} couplings in "
            f"{len(schedule.parallel_groups)} groups"
        )
        return ctx


@dataclass
class TwoQubitCalibration(CalibrationStep):
    """2-qubit coupling calibration step.

    Executes FULL_2Q_TASKS on scheduled coupling pairs.
    Uses schedule from GenerateCRSchedule if available in ctx.metadata["cr_schedule"],
    otherwise generates schedule internally.

    Requires: candidate_qids (and optionally cr_schedule in metadata)
    Provides: two_qubit, candidate_couplings
    """

    tasks: list[str] | None = None
    max_parallel_ops: int = 10

    @property
    def name(self) -> str:
        return "two_qubit_calibration"

    @property
    def requires(self) -> set[str]:
        return {"candidate_qids"}

    @property
    def provides(self) -> set[str]:
        return {"two_qubit", "candidate_couplings"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute 2-qubit calibration."""
        logger = get_run_logger()
        tasks = self.tasks or FULL_2Q_TASKS

        candidate_qubits = ctx.candidate_qids
        if len(candidate_qubits) < 2:
            logger.warning(f"[{self.name}] Not enough candidates ({len(candidate_qubits)}) for 2Q")
            ctx.two_qubit = TwoQubitResult()
            return ctx

        # Use pre-generated schedule if available, otherwise generate
        if "cr_schedule" in ctx.metadata:
            parallel_groups = ctx.metadata["cr_schedule"]
            logger.info(f"[{self.name}] Using pre-generated CR schedule")
        else:
            from qdash.workflow.engine import CRScheduler

            wiring_config_path = str(get_qubex_paths().wiring_yaml(service.chip_id))
            scheduler = CRScheduler(
                service.username,
                service.chip_id,
                wiring_config_path=wiring_config_path,
            )
            schedule = scheduler.generate(
                candidate_qubits=candidate_qubits,
                max_parallel_ops=self.max_parallel_ops,
            )
            parallel_groups = schedule.parallel_groups

        if not parallel_groups:
            logger.warning(f"[{self.name}] No valid CR pairs found")
            ctx.two_qubit = TwoQubitResult()
            return ctx

        coupling_groups = [[f"{c}-{t}" for c, t in group] for group in parallel_groups]
        total_pairs = sum(len(g) for g in coupling_groups)
        logger.info(
            f"[{self.name}] Executing {total_pairs} coupling pairs in "
            f"{len(coupling_groups)} groups"
        )

        # Execute
        from qdash.workflow.service._internal.scheduling_tasks import calibrate_parallel_group
        from qdash.workflow.service.calib_service import (
            finish_calibration,
            get_session,
            init_calibration,
        )
        from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig

        init_calibration(
            service.username,
            service.chip_id,
            candidate_qubits,
            flow_name=f"{service.flow_name}_{self.name}" if service.flow_name else self.name,
            project_id=service.project_id,
            enable_github_pull=False,
            github_push_config=GitHubPushConfig(
                enabled=True,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
            ),
            note={
                "type": "2-qubit",
                "candidate_qubits": candidate_qubits,
                "schedule": coupling_groups,
            },
        )

        all_raw_results: dict[str, Any] = {}
        for group in coupling_groups:
            group_results = calibrate_parallel_group(coupling_qids=group, tasks=tasks)
            all_raw_results.update(group_results)

        session = get_session()
        session.record_stage_result(self.name, all_raw_results)
        finish_calibration()

        # Build typed result
        result = self._build_result(all_raw_results)
        ctx.two_qubit = result

        logger.info(
            f"[{self.name}] Completed. "
            f"{len(result.successful_couplings())}/{total_pairs} successful"
        )
        return ctx

    def _build_result(self, raw_results: dict[str, Any]) -> TwoQubitResult:
        """Build typed result from raw backend data."""
        from qdash.workflow.service.results import CouplingCalibData

        result = TwoQubitResult()
        for coupling_id, raw in raw_results.items():
            if isinstance(raw, dict):
                result.add_coupling(
                    coupling_id,
                    CouplingCalibData(
                        status="success" if raw.get("status") == "success" else "failed",
                        metrics=self._extract_metrics(raw),
                        raw=raw,
                    ),
                )
        return result

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from raw result."""
        metrics = {}
        # ZX90 fidelity
        zx_irb = raw.get("ZX90InterleavedRandomizedBenchmarking", {})
        if zx_irb:
            fidelity_param = zx_irb.get("zx90_gate_fidelity")
            if fidelity_param is not None:
                metrics["zx90_fidelity"] = (
                    fidelity_param.value if hasattr(fidelity_param, "value") else fidelity_param
                )
        # Bell fidelity
        bell_result = raw.get("CheckBellState", {})
        if bell_result:
            fidelity_param = bell_result.get("bell_fidelity")
            if fidelity_param is not None:
                metrics["bell_fidelity"] = (
                    fidelity_param.value if hasattr(fidelity_param, "value") else fidelity_param
                )
        return metrics


@dataclass
class CheckSkew(CalibrationStep):
    """System-level skew check step.

    Checks timing skew across MUX channels. This is a system-level task
    that doesn't target specific qubits.

    Note: This step uses execute_task directly with qid="" for system tasks.
    """

    muxes: list[int] | None = None

    @property
    def name(self) -> str:
        return "check_skew"

    @property
    def provides(self) -> set[str]:
        return {"skew_check"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute skew check."""
        logger = get_run_logger()

        muxes = self.muxes
        if muxes is None:
            muxes = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

        logger.info(f"[{self.name}] Checking skew for {len(muxes)} MUX channels")

        # Initialize session for system task
        service._initialize([])

        try:
            raw_result = service.execute_task(
                "CheckSkew",
                qid="",
                task_details={"CheckSkew": {"muxes": muxes}},
            )

            ctx.skew_check = SkewCheckResult(
                passed=True,  # TODO: evaluate actual skew values
                raw=raw_result,
            )

            service.finish_calibration()
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            service.fail_calibration(str(e))
            raise

        logger.info(f"[{self.name}] Completed")
        return ctx
