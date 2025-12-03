"""Full chip calibration workflow with automatic Box scheduling.

Uses OneQubitScheduler to automatically group qubits by box constraints:
- Box A: Qubits using only Box A modules (can run in parallel with Box B)
- Box B: Qubits using only Box B modules (can run in parallel with Box A)
- Mixed: Qubits using both A and B modules (conflicts with both)

Workflow stages:
1. 1-qubit calibration - Automatically scheduled by Box constraints
2. CR scheduling - Automatic candidate filtering and schedule generation
3. 2-qubit calibration - Parallel coupling calibration using CR schedule

Key features:
- Automatic Box detection from wiring configuration
- MUX-based qubit grouping
- Supports exclude_qids for skipping known-bad qubits
- Each Box stage tracked with separate execution_id

Example:
    # Calibrate all qubits in MUX 0-7, excluding known-bad qubits
    scheduled_full_calibration(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3, 4, 5, 6, 7],
        exclude_qids=["5", "12", "23"],  # Skip bad qubits
    )
"""

from dataclasses import dataclass, field

from prefect import flow, get_run_logger, task

from qdash.workflow.engine.calibration import CRScheduler, OneQubitScheduler
from qdash.workflow.flow import finish_calibration, get_session, init_calibration


@dataclass
class ScheduledOneQubitStage:
    """1-qubit calibration stage with automatic Box scheduling."""

    type: str = "1qubit_scheduled"
    mux_ids: list[int] = field(default_factory=list)
    exclude_qids: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)


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
    tasks: list[str] = field(default_factory=list)


def extract_candidate_qubits(stage1_results: dict, x90_fidelity_threshold: float = 0.90) -> list[str]:
    """Extract qubits with high X90 gate fidelity from Stage 1 calibration.

    Args:
        stage1_results: Results from Stage 1 (1-qubit calibration)
        x90_fidelity_threshold: Minimum X90 gate fidelity (default: 0.90 = 90%)

    Returns:
        List of qubit IDs that meet the fidelity threshold for 2-qubit calibration
    """
    candidates = []
    for stage_name, stage_data in stage1_results.items():
        if not isinstance(stage_data, dict):
            continue
        for qid, result in stage_data.items():
            if not isinstance(result, dict):
                continue
            if result.get("status") != "success":
                continue

            # Extract X90 gate fidelity from IRB results
            irb_result = result.get("X90InterleavedRandomizedBenchmarking", {})
            x90_fidelity_param = irb_result.get("x90_gate_fidelity")

            # Handle both OutputParameterModel and raw value
            if x90_fidelity_param is not None:
                x90_fidelity = x90_fidelity_param.value if hasattr(x90_fidelity_param, "value") else x90_fidelity_param

                if x90_fidelity >= x90_fidelity_threshold:
                    candidates.append(qid)

    return sorted(set(candidates))


@task
def execute_coupling_pair(coupling_qid: str, tasks: list[str]) -> tuple[str, dict]:
    """Execute tasks for a single coupling pair with error handling."""
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
    """Execute coupling tasks for a parallel group of qubit pairs."""
    futures = [execute_coupling_pair.submit(coupling_qid, tasks) for coupling_qid in coupling_qids]
    pair_results = [future.result() for future in futures]

    results = {}
    for qid, result in pair_results:
        results[qid] = result

    return results


@task
def calibrate_qubits_sequential(qids: list[str], tasks: list[str]) -> dict:
    """Execute tasks for qubits sequentially with error handling.

    Qubits in the same Box stage are executed sequentially to avoid conflicts.

    Args:
        qids: List of qubit IDs to calibrate (executed in order)
        tasks: List of task names to execute

    Returns:
        Results for the stage (includes error information for failed qubits)
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


def execute_scheduled_one_qubit_stage(
    username: str,
    chip_id: str,
    mux_ids: list[int],
    exclude_qids: list[str],
    tasks: list[str],
    flow_name: str | None = None,
) -> dict:
    """Execute 1-qubit calibration with automatic Box scheduling.

    Uses OneQubitScheduler to automatically group qubits by Box constraints
    and executes each Box stage as a separate session.

    Args:
        username: User name
        chip_id: Chip ID
        mux_ids: List of MUX IDs to calibrate
        exclude_qids: List of qubit IDs to exclude
        tasks: List of 1-qubit task names to execute
        flow_name: Flow name for this stage

    Returns:
        Dictionary of calibration results organized by Box stage
    """
    from qdash.workflow.flow import ConfigFileType, GitHubPushConfig

    logger = get_run_logger()

    # Generate schedule using OneQubitScheduler
    wiring_config_path = f"/app/config/qubex/{chip_id}/config/wiring.yaml"
    scheduler = OneQubitScheduler(chip_id=chip_id, wiring_config_path=wiring_config_path)
    schedule = scheduler.generate_from_mux(mux_ids=mux_ids, exclude_qids=exclude_qids)

    logger.info(f"OneQubitScheduler generated {len(schedule.stages)} stages:")
    for i, stage in enumerate(schedule.stages, 1):
        logger.info(f"  Stage {i} (Box {stage.box_type}): {len(stage.qids)} qubits")

    all_stage_results = {}

    # Execute each Box stage as a separate session
    for stage_info in schedule.stages:
        stage_name = f"Box_{stage_info.box_type}"
        logger.info("=" * 50)
        logger.info(f"Executing {stage_name}: {stage_info.qids}")
        logger.info("=" * 50)

        # Initialize session for this Box stage
        init_calibration(
            username,
            chip_id,
            stage_info.qids,
            flow_name=f"{flow_name}_{stage_name}" if flow_name else stage_name,
            enable_github_pull=True,
            github_push_config=GitHubPushConfig(
                enabled=True, file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
            ),
        )

        # Execute qubits sequentially within this Box stage
        stage_results = calibrate_qubits_sequential(qids=stage_info.qids, tasks=tasks)

        # Record and finish
        session = get_session()
        session.record_stage_result(f"stage1_{stage_name}", stage_results)
        finish_calibration()

        all_stage_results[stage_name] = stage_results

    return all_stage_results


def generate_cr_schedule(
    username: str,
    chip_id: str,
    stage1_results: dict,
    flow_name: str | None = None,
    max_parallel_ops: int = 10,
    x90_fidelity_threshold: float = 0.90,
):
    """Generate CR schedule from Stage 1 calibration results."""
    logger = get_run_logger()

    candidate_qubits = extract_candidate_qubits(stage1_results, x90_fidelity_threshold)
    logger.info(f"Candidate qubits ({len(candidate_qubits)}): {candidate_qubits}")

    if len(candidate_qubits) == 0:
        return None, []

    wiring_config_path = f"/app/config/qubex/{chip_id}/config/wiring.yaml"

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
    """Execute 2-qubit calibration using CR schedule."""
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
def scheduled_full_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    flow_name: str | None = None,
):
    """Full chip calibration with automatic Box scheduling.

    Uses OneQubitScheduler to automatically detect Box constraints from wiring
    configuration and group qubits for optimal execution.

    Workflow:
    1. OneQubitScheduler analyzes wiring config and creates Box-based stages
    2. Each Box stage (A, B, Mixed) executes as a separate session
    3. CR scheduling filters candidates by X90 fidelity
    4. 2-qubit calibration runs on filtered pairs

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: List of MUX IDs to calibrate. If None, uses all 16 MUXes (0-15)
        exclude_qids: List of qubit IDs to exclude from calibration (e.g., known-bad qubits)
        qids: Not used (for UI compatibility only)
        flow_name: Flow name (auto-injected)

    Example:
        # Calibrate MUX 0-7, excluding qubits 5 and 12
        scheduled_full_calibration(
            username="alice",
            chip_id="64Qv3",
            mux_ids=[0, 1, 2, 3, 4, 5, 6, 7],
            exclude_qids=["5", "12"],
        )

        # Calibrate all 64 qubits (default: MUX 0-15)
        scheduled_full_calibration(
            username="alice",
            chip_id="64Qv3",
        )
    """
    logger = get_run_logger()

    # Default to all 16 MUXes for 64Q chip
    if mux_ids is None:
        mux_ids = list(range(16))

    if exclude_qids is None:
        exclude_qids = []

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

    # 2-qubit calibration tasks
    two_qubit_tasks = [
        "CheckCrossResonance",
        "CreateZX90",
        "CheckZX90",
        "CheckBellState",
    ]

    stages = [
        # Stage 1: 1-qubit calibration with automatic Box scheduling
        ScheduledOneQubitStage(
            mux_ids=mux_ids,
            exclude_qids=exclude_qids,
            tasks=full_1q_tasks,
        ),
        # Stage 2: CR Scheduling
        CRScheduleStage(
            max_parallel_ops=10,
            x90_fidelity_threshold=0.90,
        ),
        # Stage 3: 2-qubit calibration
        TwoQubitStage(
            tasks=two_qubit_tasks,
        ),
    ]

    logger.info(f"Starting scheduled calibration workflow for chip_id={chip_id}")
    logger.info(f"MUX IDs: {mux_ids}")
    logger.info(f"Excluded qubits: {exclude_qids}")
    logger.info(f"Total stages: {len(stages)}")

    all_results = {}
    schedule_result = None
    candidate_qubits = []

    try:
        for stage_idx, stage in enumerate(stages, start=1):
            logger.info("=" * 60)
            logger.info(f"STAGE {stage_idx}: {stage.type}")
            logger.info("=" * 60)

            if isinstance(stage, ScheduledOneQubitStage):
                stage_results = execute_scheduled_one_qubit_stage(
                    username=username,
                    chip_id=chip_id,
                    mux_ids=stage.mux_ids,
                    exclude_qids=stage.exclude_qids,
                    tasks=stage.tasks,
                    flow_name=flow_name,
                )
                all_results["1qubit"] = stage_results

            elif isinstance(stage, CRScheduleStage):
                schedule_result, candidate_qubits = generate_cr_schedule(
                    username=username,
                    chip_id=chip_id,
                    stage1_results=all_results.get("1qubit", {}),
                    flow_name=flow_name,
                    max_parallel_ops=stage.max_parallel_ops,
                    x90_fidelity_threshold=stage.x90_fidelity_threshold,
                )

                if schedule_result is not None:
                    all_results["cr_schedule"] = schedule_result.to_dict()
                else:
                    logger.warning("No candidate qubits found, skipping 2-qubit calibration")

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
                all_results["2qubit"] = stage2_results

            else:
                logger.warning(f"Unknown stage type '{type(stage).__name__}', skipping")

        logger.info("=" * 60)
        logger.info("Scheduled calibration completed successfully!")
        logger.info("=" * 60)

        return all_results

    except Exception as e:
        logger.error(f"Scheduled calibration failed: {e}")
        try:
            session = get_session()
            session.fail_calibration(str(e))
        except RuntimeError:
            pass
        raise
