"""Full chip calibration workflow: 1-qubit → CR scheduling → 2-qubit.

Complete end-to-end calibration workflow for quantum chips with automatic
quality filtering and hardware constraint management.

Workflow stages:
1. 1-qubit calibration - Full characterization (Rabi, T1/T2, DRAG, RB/IRB)
2. CR scheduling - Automatic candidate filtering and schedule generation
3. 2-qubit calibration - Parallel coupling calibration using CR schedule

Key features:
- Automatic quality filtering (X90 gate fidelity ≥90%)
- Hardware constraints handled (MUX conflicts, frequency directionality)
- Optimized parallel execution via graph coloring
- Each stage tracked with separate execution_id
- Flexible stage configuration using dataclasses

Stage classes:
- OneQubitStage: 1-qubit calibration with groups and tasks
- CRScheduleStage: CR scheduling with filtering parameters
- TwoQubitStage: 2-qubit calibration with tasks
"""

from dataclasses import dataclass

from prefect import flow, get_run_logger, task
from qdash.workflow.engine.calibration import CRScheduler
from qdash.workflow.flow import finish_calibration, get_session, init_calibration


@dataclass
class OneQubitStage:
    """1-qubit calibration stage configuration."""

    type: str = "1qubit"
    name: str = ""
    groups: list[list[str]] = None
    tasks: list[str] = None

    def __post_init__(self):
        if self.groups is None:
            self.groups = []
        if self.tasks is None:
            self.tasks = []


@dataclass
class CRScheduleStage:
    """CR scheduling stage configuration."""

    type: str = "cr_schedule"
    name: str = "CR_Schedule"
    max_parallel_ops: int = 10
    x90_fidelity_threshold: float = 0.90


@dataclass
class TwoQubitStage:
    """2-qubit calibration stage configuration."""

    type: str = "2qubit"
    name: str = "2Qubit_Calibration"
    tasks: list[str] = None

    def __post_init__(self):
        if self.tasks is None:
            self.tasks = []


def extract_candidate_qubits(stage1_results: dict, x90_fidelity_threshold: float = 0.90) -> list[str]:
    """Extract qubits with high X90 gate fidelity from Stage 1 calibration.

    Args:
    ----
        stage1_results: Results from Stage 1 (1-qubit calibration)
        x90_fidelity_threshold: Minimum X90 gate fidelity (default: 0.90 = 90%)

    Returns:
    -------
        List of qubit IDs that meet the fidelity threshold for 2-qubit calibration

    """
    candidates = []
    for stage_name, stage_data in stage1_results.items():
        for qid, result in stage_data.items():
            if result.get("status") != "success":
                continue

            # Extract X90 gate fidelity from IRB results
            irb_result = result.get("X90InterleavedRandomizedBenchmarking", {})
            x90_fidelity_param = irb_result.get("x90_gate_fidelity")

            # Handle both OutputParameterModel and raw value
            if x90_fidelity_param is not None:
                # If it's an OutputParameterModel, get .value; otherwise use directly
                x90_fidelity = x90_fidelity_param.value if hasattr(x90_fidelity_param, "value") else x90_fidelity_param

                if x90_fidelity >= x90_fidelity_threshold:
                    candidates.append(qid)

    return sorted(set(candidates))


@task
def execute_coupling_pair(coupling_qid: str, tasks: list[str]) -> tuple[str, dict]:
    """Execute tasks for a single coupling pair with error handling.

    Args:
    ----
        coupling_qid: Coupling ID in "control-target" format (e.g., "0-1")
        tasks: List of coupling task names to execute

    Returns:
    -------
        Tuple of (coupling_qid, result dict)

    """
    logger = get_run_logger()
    session = get_session()

    try:
        result = {}
        for task_name in tasks:
            task_result = session.execute_task(task_name, coupling_qid)
            result[task_name] = task_result
        result["status"] = "success"

    except Exception as e:
        logger.error(f"Failed to calibrate coupling {coupling_qid}: {e}")
        result = {"status": "failed", "error": str(e)}

    return coupling_qid, result


@task
def calibrate_parallel_group_coupling(coupling_qids: list[str], tasks: list[str]) -> dict:
    """Execute coupling tasks for a parallel group of qubit pairs with error handling.

    All coupling pairs in this group run in parallel since they don't share qubits.
    If a coupling pair fails during calibration, it will be marked as failed in the results.

    Args:
    ----
        coupling_qids: List of coupling IDs in "control-target" format (e.g., ["0-1", "2-3"])
                       All pairs in this list can run simultaneously (no shared qubits)
        tasks: List of coupling task names to execute

    Returns:
    -------
        Results for the parallel group (includes error information for failed pairs)

    """
    futures = [execute_coupling_pair.submit(coupling_qid, tasks) for coupling_qid in coupling_qids]
    pair_results = [future.result() for future in futures]

    results = {}
    for qid, result in pair_results:
        results[qid] = result

    return results


@task
def calibrate_group(qids: list[str], tasks: list[str]) -> dict:
    """Execute tasks for a group of qubits sequentially with error handling.

    If a qubit fails during calibration, it will be skipped and the next qubit
    will be processed. Failed qubits are logged and marked in the results.

    Args:
    ----
        qids: List of qubit IDs to calibrate (executed in order)
        tasks: List of task names to execute

    Returns:
    -------
        Results for the group (includes error information for failed qubits)

    """
    logger = get_run_logger()
    session = get_session()
    results = {}

    for qid in qids:
        try:
            result = {}
            for task_name in tasks:
                task_result = session.execute_task(task_name, qid)
                result[task_name] = task_result
            result["status"] = "success"

        except Exception as e:
            logger.error(f"Failed to calibrate qubit {qid}: {e}")
            result = {"status": "failed", "error": str(e)}

        results[qid] = result

    return results


def execute_one_qubit_stage(
    username: str,
    chip_id: str,
    stage_name: str,
    stage_groups: list[list[str]],
    stage_tasks: list[str],
    flow_name: str | None = None,
) -> dict:
    """Execute 1-qubit calibration stage.

    Args:
    ----
        username: User name
        chip_id: Chip ID
        stage_name: Name of this stage
        stage_groups: Groups of qubit IDs (parallel execution within groups)
        stage_tasks: List of 1-qubit task names to execute
        flow_name: Flow name for this stage

    Returns:
    -------
        Dictionary of calibration results

    """
    from qdash.workflow.flow import ConfigFileType, GitHubPushConfig

    # Flatten qids for this stage
    stage_qids = list(set(qid for group in stage_groups for qid in group))

    # Initialize NEW session for this stage
    init_calibration(
        username,
        chip_id,
        stage_qids,
        flow_name=f"{flow_name}_{stage_name}" if flow_name else stage_name,
        enable_github_pull=True,
        github_push_config=GitHubPushConfig(
            enabled=True, file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
        ),
    )

    # Execute all groups in parallel
    stage_futures = [calibrate_group.submit(qids=group, tasks=stage_tasks) for group in stage_groups]
    stage_results_list = [future.result() for future in stage_futures]

    # Combine results
    stage_results = {}
    for results in stage_results_list:
        stage_results.update(results)

    # Record and finish
    session = get_session()
    session.record_stage_result(f"stage1_{stage_name}", stage_results)
    finish_calibration()

    return stage_results


def generate_cr_schedule(
    username: str,
    chip_id: str,
    stage1_results: dict,
    flow_name: str | None = None,
    max_parallel_ops: int = 10,
    x90_fidelity_threshold: float = 0.90,
):
    """Generate CR schedule from Stage 1 calibration results.

    Args:
    ----
        username: User name
        chip_id: Chip ID
        stage1_results: Results from Stage 1 (1-qubit calibration)
        flow_name: Flow name for this stage
        max_parallel_ops: Maximum parallel operations per group
        x90_fidelity_threshold: Minimum X90 gate fidelity threshold

    Returns:
    -------
        Tuple of (schedule_result, candidate_qubits) or (None, []) if no candidates

    """
    logger = get_run_logger()

    candidate_qubits = extract_candidate_qubits(stage1_results, x90_fidelity_threshold)
    logger.info(f"Candidate qubits: {candidate_qubits}")

    if len(candidate_qubits) == 0:
        return None, []

    # Get wiring config path (no session needed for CR scheduling)
    wiring_config_path = f"/app/config/{username}/{chip_id}/wiring.yaml"

    scheduler = CRScheduler(username, chip_id, wiring_config_path=wiring_config_path)
    schedule_result = scheduler.generate(
        candidate_qubits=candidate_qubits,
        max_parallel_ops=max_parallel_ops,
    )

    logger.info(f"CR schedule: {schedule_result}")

    return schedule_result, candidate_qubits


def execute_two_qubit_calibration(
    username: str,
    chip_id: str,
    schedule_result,
    candidate_qubits: list[str],
    tasks: list[str],
    flow_name: str | None = None,
):
    """Execute 2-qubit calibration using CR schedule.

    Args:
    ----
        username: User name
        chip_id: Chip ID
        schedule_result: CR schedule result from generate_cr_schedule
        candidate_qubits: List of candidate qubit IDs
        tasks: List of 2-qubit task names to execute
        flow_name: Flow name for this stage

    Returns:
    -------
        Dictionary of Stage 2 calibration results

    """
    logger = get_run_logger()
    from qdash.workflow.flow import ConfigFileType, GitHubPushConfig

    parallel_groups = schedule_result.parallel_groups
    coupling_qid_groups = [[f"{c}-{t}" for c, t in group] for group in parallel_groups]

    total_pairs = schedule_result.metadata.get("scheduled_pairs", 0)
    logger.info(f"Executing {total_pairs} coupling pairs in {len(parallel_groups)} parallel groups")

    init_calibration(
        username,
        chip_id,
        candidate_qubits,
        flow_name=f"{flow_name}_Stage2_2Qubit" if flow_name else "Stage2_2Qubit",
        enable_github_pull=False,
        github_push_config=GitHubPushConfig(
            enabled=True, file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
        ),
    )

    # Execute parallel groups sequentially
    stage2_results_list = []
    for group in coupling_qid_groups:
        result = calibrate_parallel_group_coupling(coupling_qids=group, tasks=tasks)
        stage2_results_list.append(result)

    # Combine and record results
    stage2_results = {}
    for r in stage2_results_list:
        stage2_results.update(r)

    session = get_session()
    session.record_stage_result("stage2_2qubit", stage2_results)
    finish_calibration()

    return stage2_results


@flow
def full_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
):
    """Full chip calibration workflow: 1-qubit → CR scheduling → 2-qubit.

    Complete end-to-end calibration workflow for quantum chips:

    Stage 1: 1-qubit calibration
    - Full characterization: Rabi, T1/T2, DRAG, RB/IRB
    - Multiple chassis can run sequentially with isolated sessions
    - Each chassis gets its own execution_id

    Stage 2: CR scheduling
    - Automatically filters candidates by X90 gate fidelity ≥90%
    - Generates optimized parallel execution schedule
    - Handles MUX conflicts and frequency directionality
    - Uses graph coloring for maximum parallelization

    Stage 3: 2-qubit calibration
    - Executes coupling calibration using CR schedule
    - Parallel execution within groups (no qubit sharing)
    - Tasks: CheckCrossResonance, CreateZX90, CheckZX90, CheckBellState

    Benefits:
    - End-to-end automation from 1-qubit to 2-qubit
    - Automatic quality filtering between stages
    - Hardware constraints handled automatically
    - Each stage tracked with separate execution_id

    Args:
    ----
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Qubit IDs (not used, defined explicitly in stages)
        flow_name: Flow name (auto-injected)

    """
    logger = get_run_logger()

    # TODO: Define complete workflow as stages
    # Each stage runs independently with its own execution_id
    # Stage types: OneQubitStage, CRScheduleStage, TwoQubitStage

    # Common 1-qubit calibration tasks
    full_1q_tasks = [
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CreatePIPulse",
        "CheckPIPulse",
        "CheckT1",
        "CheckT2Echo",
        "CreateDRAGHPIPulse",
        "CheckDRAGHPIPulse",
        "CreateDRAGPIPulse",
        "CheckDRAGPIPulse",
        "ReadoutClassification",
        "RandomizedBenchmarking",
        "X90InterleavedRandomizedBenchmarking",
    ]

    stages = [
        # Stage 1: 1-qubit calibration for Chassis A
        OneQubitStage(
            name="Chassis_A",
            groups=[["0", "1"], ["2"]],
            tasks=full_1q_tasks,
        ),
        # Stage 2: 1-qubit calibration for Chassis B
        OneQubitStage(
            name="Chassis_B",
            groups=[["3", "4"], ["5"]],
            tasks=full_1q_tasks,
        ),
        # Stage 3: CR Scheduling
        CRScheduleStage(
            max_parallel_ops=10,
            x90_fidelity_threshold=0.90,
        ),
        # Stage 4: 2-qubit calibration
        TwoQubitStage(
            tasks=[
                "CheckCrossResonance",
                "CreateZX90",
                "CheckZX90",
                "CheckBellState",
            ],
        ),
    ]

    logger.info(f"Starting multi-stage calibration workflow for chip_id={chip_id}")
    logger.info(f"Total stages: {len(stages)}")
    for i, stage in enumerate(stages, start=1):
        if isinstance(stage, OneQubitStage):
            logger.info(f"  Stage {i} ({stage.name}): 1-qubit calibration, {sum(len(g) for g in stage.groups)} qubits")
        elif isinstance(stage, CRScheduleStage):
            logger.info(f"  Stage {i} ({stage.name}): CR scheduling")
        elif isinstance(stage, TwoQubitStage):
            logger.info(f"  Stage {i} ({stage.name}): 2-qubit calibration")

    all_results = {}
    schedule_result = None
    candidate_qubits = []

    try:
        # Execute each stage sequentially
        for stage_idx, stage in enumerate(stages, start=1):
            logger.info("=" * 60)
            logger.info(f"STAGE {stage_idx}: {stage.name}")
            logger.info("=" * 60)

            if isinstance(stage, OneQubitStage):
                stage_results = execute_one_qubit_stage(
                    username=username,
                    chip_id=chip_id,
                    stage_name=stage.name,
                    stage_groups=stage.groups,
                    stage_tasks=stage.tasks,
                    flow_name=flow_name,
                )
                all_results[stage.name] = stage_results

            elif isinstance(stage, CRScheduleStage):
                schedule_result, candidate_qubits = generate_cr_schedule(
                    username=username,
                    chip_id=chip_id,
                    stage1_results=all_results,
                    flow_name=flow_name,
                    max_parallel_ops=stage.max_parallel_ops,
                    x90_fidelity_threshold=stage.x90_fidelity_threshold,
                )

                if schedule_result is not None:
                    all_results["cr_schedule"] = schedule_result.to_dict()
                else:
                    logger.warning("No candidate qubits found, skipping subsequent 2-qubit stages")

            elif isinstance(stage, TwoQubitStage):
                if schedule_result is None:
                    logger.warning(f"Skipping {stage.name} (no CR schedule available)")
                    continue

                stage2_results = execute_two_qubit_calibration(
                    username=username,
                    chip_id=chip_id,
                    schedule_result=schedule_result,
                    candidate_qubits=candidate_qubits,
                    tasks=stage.tasks,
                    flow_name=flow_name,
                )
                all_results[stage.name] = stage2_results

            else:
                logger.warning(f"Unknown stage type '{type(stage).__name__}', skipping")

        logger.info("=" * 60)
        logger.info("Multi-stage calibration completed successfully!")
        logger.info("=" * 60)

        return all_results

    except Exception as e:
        logger.error(f"Sequential stage calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            pass
        raise
