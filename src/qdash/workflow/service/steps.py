"""Step classes for calibration workflows.

This module defines the Step abstraction for building calibration pipelines.
Steps are composable units of calibration work that can be chained together.

Each step declares:
- `requires`: Context keys it needs from previous steps
- `provides`: Context keys it produces

Example:
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.targets import MuxTargets
    from qdash.workflow.service.steps import (
        OneQubitCheck,
        OneQubitFineTune,
        FilterByMetric,
        TwoQubitCalibration,
    )

    service = CalibService(username, chip_id)
    targets = MuxTargets([0, 1, 2, 3])

    steps = [
        OneQubitCheck(),
        OneQubitFineTune(),
        FilterByMetric(metric="x90_fidelity", threshold=0.9),
        TwoQubitCalibration(),
    ]

    results = service.run(targets, steps=steps)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator

from prefect import get_run_logger
from qdash.workflow.service.results import (
    FilterResult,
    OneQubitResult,
    SkewCheckResult,
    TwoQubitResult,
)
from qdash.workflow.service.targets import Target
from qdash.workflow.service.tasks import (
    CHECK_1Q_TASKS,
    FULL_1Q_TASKS_AFTER_CHECK,
    FULL_2Q_TASKS,
)

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


# =============================================================================
# Context and Base Classes
# =============================================================================


@dataclass
class StepContext:
    """Context shared between steps in a calibration pipeline.

    This context is passed through all steps and accumulates typed results.
    Filter steps modify `candidate_qids` to affect subsequent steps.

    Attributes:
        one_qubit_check: Result from OneQubitCheck step
        one_qubit_fine_tune: Result from OneQubitFineTune step
        two_qubit: Result from TwoQubitCalibration step
        filters: List of filter results applied
        skew_check: Result from CheckSkew step
        candidate_qids: Current list of candidate qubit IDs (can be filtered)
        candidate_couplings: Current list of candidate coupling IDs
        metadata: Additional metadata for the pipeline run
    """

    # Typed step results
    one_qubit_check: OneQubitResult | None = None
    one_qubit_fine_tune: OneQubitResult | None = None
    two_qubit: TwoQubitResult | None = None
    filters: list[FilterResult] = field(default_factory=list)
    skew_check: SkewCheckResult | None = None

    # Candidate tracking
    candidate_qids: list[str] = field(default_factory=list)
    candidate_couplings: list[str] = field(default_factory=list)

    # Generic storage
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_latest_one_qubit_result(self) -> OneQubitResult | None:
        """Get the most recent 1-qubit result (fine_tune if available, else check)."""
        return self.one_qubit_fine_tune or self.one_qubit_check


@dataclass
class Step(ABC):
    """Abstract base class for calibration steps.

    Steps are composable units of work in a calibration pipeline.
    Each step declares its dependencies (requires) and outputs (provides).

    Subclasses must implement:
        - name: Step identifier
        - execute: Main execution logic
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Step name for identification."""
        ...

    @property
    def requires(self) -> set[str]:
        """Context keys this step requires from previous steps.

        Override to declare dependencies. Default: no requirements.
        """
        return set()

    @property
    def provides(self) -> set[str]:
        """Context keys this step provides.

        Override to declare outputs. Default: {self.name}.
        """
        return {self.name}

    @abstractmethod
    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute the step.

        Args:
            service: CalibService instance (provides execute_task, etc.)
            targets: Target specification
            ctx: Current pipeline context

        Returns:
            Updated StepContext with results
        """
        ...


# =============================================================================
# Pipeline
# =============================================================================


@dataclass
class Pipeline:
    """A validated sequence of calibration steps.

    Pipeline validates step dependencies at construction time,
    ensuring all required context keys are available before each step runs.

    Example:
        pipeline = Pipeline([
            OneQubitCheck(),
            FilterByMetric(metric="t1", threshold=30.0),
            TwoQubitCalibration(),
        ])
        # Raises ValueError if dependencies are not satisfied
    """

    steps: list[Step]

    def __post_init__(self) -> None:
        """Validate step dependencies."""
        self._validate()

    def _validate(self) -> None:
        """Validate that all step dependencies are satisfied.

        Raises:
            ValueError: If a step requires context keys that no previous step provides
        """
        # Initial context always has these available
        available: set[str] = {"candidate_qids", "candidate_couplings"}

        for step in self.steps:
            # Check if all requirements are met
            # For "or" requirements (like one_qubit_check OR one_qubit_fine_tune),
            # we check if ANY of them is available
            missing = step.requires - available
            if missing:
                # Check if this is an "or" requirement situation
                # FilterByMetric/FilterByStatus require one_qubit_check | one_qubit_fine_tune
                # meaning they need at least one of them
                if not (step.requires & available):
                    raise ValueError(
                        f"Step '{step.name}' requires {step.requires}, "
                        f"but only {available} are available. "
                        f"Missing: {missing}"
                    )

            # Add what this step provides
            available.update(step.provides)

    def __iter__(self) -> Iterator[Step]:
        """Iterate over steps."""
        return iter(self.steps)

    def __len__(self) -> int:
        """Return number of steps."""
        return len(self.steps)


# =============================================================================
# 1-Qubit Calibration Steps
# =============================================================================


@dataclass
class CustomOneQubit(Step):
    """Custom 1-qubit calibration step with user-defined tasks.

    This is the most flexible 1-qubit step - you specify exactly which
    tasks to run. Use this when the predefined steps don't fit your needs.

    Example:
        # Run specific tasks
        CustomOneQubit(
            name="frequency_check",
            tasks=["CheckQubitSpectroscopy", "CheckFrequency"],
        )

        # Run T1/T2 characterization only
        CustomOneQubit(
            name="coherence_check",
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
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
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
        ctx.candidate_qids = result.successful_qids()

        logger.info(f"[{self.name}] Completed. {len(ctx.candidate_qids)} successful qubits")
        return ctx

    def _execute_direct(
        self,
        service: CalibService,
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
class OneQubitCheck(Step):
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
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
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

        # Build typed result (Step is responsible for parsing backend-specific data)
        result = self._build_result(raw_results)
        ctx.one_qubit_check = result
        ctx.candidate_qids = result.successful_qids()

        logger.info(f"[{self.name}] Completed. {len(ctx.candidate_qids)} successful qubits")
        return ctx

    def _execute_direct(
        self,
        service: CalibService,
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
        """Build typed result from raw backend data. Backend-specific parsing here."""
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
        """Extract metrics from raw result. Override for different backends."""
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
class OneQubitFineTune(Step):
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
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute 1-qubit fine-tuning calibration."""
        logger = get_run_logger()
        tasks = self.tasks or FULL_1Q_TASKS_AFTER_CHECK

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

        result = self._build_result(raw_results)
        ctx.one_qubit_fine_tune = result
        ctx.candidate_qids = result.successful_qids()

        logger.info(f"[{self.name}] Completed. {len(ctx.candidate_qids)} successful qubits")
        return ctx

    def _execute_direct(
        self,
        service: CalibService,
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
        """Extract metrics from raw result. Backend-specific parsing."""
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


# =============================================================================
# Filter Steps
# =============================================================================


@dataclass
class FilterByMetric(Step):
    """Filter qubits by a named metric threshold.

    This step filters `ctx.candidate_qids` to only include qubits
    that meet the metric threshold from the latest 1-qubit result.

    Requires: one_qubit_check or one_qubit_fine_tune
    Provides: filter result appended to ctx.filters
    """

    metric: str = "x90_fidelity"
    threshold: float = 0.9

    @property
    def name(self) -> str:
        return f"filter_by_{self.metric}"

    @property
    def requires(self) -> set[str]:
        return {"one_qubit_check"} | {"one_qubit_fine_tune"}

    @property
    def provides(self) -> set[str]:
        return {"candidate_qids"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Filter candidate qubits by metric threshold."""
        logger = get_run_logger()

        result = ctx.get_latest_one_qubit_result()
        if result is None:
            logger.warning(f"[{self.name}] No 1-qubit results found, keeping all candidates")
            return ctx

        input_qids = ctx.candidate_qids.copy()
        output_qids = result.filter_by_metric(self.metric, self.threshold)

        # Intersect with current candidates
        output_qids = sorted(set(output_qids) & set(input_qids))

        logger.info(
            f"[{self.name}] Filtered {len(input_qids)} -> {len(output_qids)} qubits "
            f"({self.metric} >= {self.threshold})"
        )

        ctx.candidate_qids = output_qids
        ctx.filters.append(
            FilterResult(
                input_qids=input_qids,
                output_qids=output_qids,
                filter_criteria=f"{self.metric} >= {self.threshold}",
            )
        )
        return ctx


@dataclass
class FilterByStatus(Step):
    """Filter qubits by calibration status.

    Keeps only qubits that have "success" status in the latest result.

    Requires: one_qubit_check or one_qubit_fine_tune
    Provides: candidate_qids
    """

    @property
    def name(self) -> str:
        return "filter_by_status"

    @property
    def requires(self) -> set[str]:
        return {"one_qubit_check"} | {"one_qubit_fine_tune"}

    @property
    def provides(self) -> set[str]:
        return {"candidate_qids"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Filter candidate qubits by success status."""
        logger = get_run_logger()

        result = ctx.get_latest_one_qubit_result()
        if result is None:
            logger.warning(f"[{self.name}] No 1-qubit results found")
            return ctx

        input_qids = ctx.candidate_qids.copy()
        output_qids = result.successful_qids()

        # Intersect with current candidates
        output_qids = sorted(set(output_qids) & set(input_qids))

        logger.info(f"[{self.name}] Filtered {len(input_qids)} -> {len(output_qids)} qubits")

        ctx.candidate_qids = output_qids
        ctx.filters.append(
            FilterResult(
                input_qids=input_qids,
                output_qids=output_qids,
                filter_criteria="status == success",
            )
        )
        return ctx


# =============================================================================
# 2-Qubit Calibration Steps
# =============================================================================


@dataclass
class CustomTwoQubit(Step):
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
            from qdash.workflow.engine.calibration import CRScheduler

            wiring_config_path = f"/app/config/qubex/{service.chip_id}/config/wiring.yaml"
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
        from qdash.workflow.service._internal.prefect_tasks import calibrate_parallel_group
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
        ctx.candidate_couplings = result.successful_couplings()

        logger.info(
            f"[{self.name}] Completed. {len(ctx.candidate_couplings)}/{total_pairs} successful"
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
        """Extract metrics from raw result.

        Custom steps don't auto-extract metrics - raw data is available via result.raw.
        Users can subclass and override this for specific metric extraction.
        """
        return {}


@dataclass
class GenerateCRSchedule(Step):
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

        from qdash.workflow.engine.calibration import CRScheduler

        wiring_config_path = f"/app/config/qubex/{service.chip_id}/config/wiring.yaml"
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
class TwoQubitCalibration(Step):
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
            from qdash.workflow.engine.calibration import CRScheduler

            wiring_config_path = f"/app/config/qubex/{service.chip_id}/config/wiring.yaml"
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
        from qdash.workflow.service._internal.prefect_tasks import calibrate_parallel_group
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
        ctx.candidate_couplings = result.successful_couplings()

        logger.info(
            f"[{self.name}] Completed. {len(ctx.candidate_couplings)}/{total_pairs} successful"
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
        """Extract metrics from raw result. Backend-specific parsing."""
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


# =============================================================================
# System Steps
# =============================================================================


@dataclass
class CheckSkew(Step):
    """System-level skew check step.

    Checks timing skew across MUX channels.
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

        raw_result = service.check_skew(muxes=muxes)

        ctx.skew_check = SkewCheckResult(
            passed=True,  # TODO: evaluate actual skew values
            raw=raw_result,
        )

        logger.info(f"[{self.name}] Completed")
        return ctx
