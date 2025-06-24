import asyncio
from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger, task
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from qdash.datamodel.menu import BatchNode, ParallelNode, ScheduleNode, SerialNode
from qdash.datamodel.menu import MenuModel as Menu
from qdash.datamodel.task import (
    CouplingTaskModel,
    GlobalTaskModel,
    QubitTaskModel,
    SystemTaskModel,
    TaskResultModel,
)
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.parameter import ParameterDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow.core.calibration.execution_manager import ExecutionManager
from qdash.workflow.core.calibration.task import (
    execute_dynamic_task_batch,
    execute_dynamic_task_by_qid,
    validate_task_name,
)
from qdash.workflow.core.calibration.task_manager import TaskManager
from qdash.workflow.core.calibration.util import (
    coupling_qids_to_qubit_labels,
    qid_to_label,
    update_active_output_parameters,
    update_active_tasks,
)
from qdash.workflow.core.session.base import BaseSession
from qdash.workflow.core.session.factory import create_session
from qdash.workflow.tasks.active_protocols import generate_task_instances


def build_workflow(
    task_names: list[str], qubits: list[str], task_details: dict[str, Any], backend: str
) -> TaskResultModel:
    """Build a workflow model for task execution.

    Constructs a TaskResultModel that represents the execution flow of tasks,
    handling different types of tasks (system, global, qubit, coupling) and
    maintaining their dependencies through upstream IDs.

    Args:
    ----
        task_names: List of task names to be executed
        qubits: List of qubit IDs involved in the workflow
        backend: Backend identifier for the tasks
        task_details: Dictionary containing task-specific configuration details

    Returns:
    -------
        TaskResultModel containing the structured workflow with task dependencies

    Raises:
    ------
        ValueError: If a task name is not found or task type is invalid

    """
    task_result = TaskResultModel()
    global_previous_task_id = ""
    qubit_previous_task_id = {qubit: "" for qubit in qubits}
    coupling_previous_task_id = {qubit: "" for qubit in qubits}
    task_instances = generate_task_instances(
        task_names=task_names, task_details=task_details, backend=backend
    )
    for name in task_names:
        if name in task_instances:
            this_task = task_instances[name]
            if this_task.is_system_task():
                # Skip system task
                task = SystemTaskModel(name=name, upstream_id=global_previous_task_id)
                task_result.system_tasks.append(task)
                global_previous_task_id = task.task_id
            elif this_task.is_global_task():
                task = GlobalTaskModel(name=name, upstream_id=global_previous_task_id)
                task_result.global_tasks.append(task)
                global_previous_task_id = task.task_id
            elif this_task.is_qubit_task():
                for qubit in qubits:
                    task = QubitTaskModel(
                        name=name, upstream_id=qubit_previous_task_id[qubit], qid=qubit
                    )
                    task_result.qubit_tasks.setdefault(qubit, []).append(task)
                    qubit_previous_task_id[qubit] = task.task_id
            elif this_task.is_coupling_task():
                for qubit in qubits:
                    task = CouplingTaskModel(
                        name=name, upstream_id=coupling_previous_task_id[qubit], qid=qubit
                    )
                    task_result.coupling_tasks.setdefault(qubit, []).append(task)
                    coupling_previous_task_id[qubit] = task.task_id
            else:
                raise ValueError(f"Task type {this_task.get_task_type()} not found.")
        else:
            raise ValueError(f"Task {name} not found.")
    return task_result


@flow(flow_run_name="{qid}")
def cal_serial(
    menu: Menu,
    session: BaseSession,
    task_manager: TaskManager,
    task_names: list[str],
    qid: str,
) -> TaskManager:
    """Execute calibration tasks sequentially for a single qubit.

    Args:
    ----
        menu: Menu configuration containing task details
        session: BaseSession instance for task execution
        task_manager: Task manager instance to track execution state
        task_names: List of task names to execute
        qid: Target qubit ID

    Returns:
    -------
        Updated TaskManager instance after task execution

    Note:
    ----
        Tasks are executed one by one, checking completion status before execution.
        Error handling ensures graceful failure and proper cleanup.

    """
    logger = get_run_logger()
    try:
        task_instances = generate_task_instances(
            task_names=task_names, task_details=menu.task_details, backend=session.name
        )
        for task_name in task_names:
            if task_name in task_instances:
                task_type = task_instances[task_name].get_task_type()
                if task_manager.this_task_is_completed(
                    task_name=task_name, task_type=task_type, qid=qid
                ):
                    logger.info(f"Task {task_name} is already completed")
                    continue
                logger.info(f"Starting task: {task_name}")
                task_instance = task_instances[task_name]
                execution_manager = ExecutionManager(
                    username=task_manager.username,
                    execution_id=task_manager.execution_id,
                    calib_data_path=task_manager.calib_dir,
                ).reload()
                execution_manager, task_manager = execute_dynamic_task_by_qid.with_options(
                    timeout_seconds=task_instance.timeout,
                    task_run_name=task_instance.name,
                    log_prints=True,
                )(
                    session=session,
                    execution_manager=execution_manager,
                    task_manager=task_manager,
                    task_instance=task_instance,
                    qid=qid,
                )
    except Exception as e:
        logger.error(f"Failed to execute {task_instance.name}: {e}, id: {task_manager.id}")
        # エラー時の処理
        task_manager.update_task_status_to_failed(
            task_name=task_name, message=f"{task_name} failed", task_type=task_type, qid=qid
        )
        task_manager.save()
        # Update task result history
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(
            task=executed_task, execution_model=execution_manager.to_datamodel()
        )
        execution_manager = execution_manager.update_with_task_manager(task_manager)
        # 未実行タスクのスキップ処理
        task_manager.update_not_executed_tasks_to_skipped(task_type=task_type, qid=qid)
        task_manager.save()
        execution_manager = execution_manager.update_with_task_manager(task_manager)
    finally:
        logger.info("Ending all processes")
    return task_manager


@flow(flow_run_name="{qids}")
def cal_batch(
    menu: Menu,
    session: BaseSession,
    task_manager: TaskManager,
    task_names: list[str],
    qids: list[str],
) -> TaskManager:
    """Execute calibration tasks in batch mode for multiple qubits.

    Args:
    ----
        menu: Menu configuration containing task details
        session: BaseSession instance for task execution
        task_manager: Task manager instance to track execution state
        task_names: List of task names to execute
        qids: List of target qubit IDs

    Returns:
    -------
        Updated TaskManager instance after task execution

    Note:
    ----
        Tasks are executed in batch mode for all specified qubits simultaneously.
        Error handling ensures graceful failure and proper cleanup.

    """
    logger = get_run_logger()
    try:
        task_instances = generate_task_instances(
            task_names=task_names, task_details=menu.task_details
        )
        for task_name in task_names:
            if task_name in task_instances:
                task_type = task_instances[task_name].get_task_type()
                logger.info(f"Starting task: {task_name}")
                task_instance = task_instances[task_name]
                execution_manager = ExecutionManager(
                    username=task_manager.username,
                    execution_id=task_manager.execution_id,
                    calib_data_path=task_manager.calib_dir,
                ).reload()
                execution_manager, task_manager = execute_dynamic_task_batch.with_options(
                    timeout_seconds=task_instance.timeout, task_run_name=task_instance.name
                )(
                    session=session,
                    execution_manager=execution_manager,
                    task_manager=task_manager,
                    task_instance=task_instance,
                    qids=qids,
                )
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
        for qid in qids:
            task_manager.update_task_status_to_failed(
                task_name=task_name, message=f"{task_name} failed", task_type=task_type, qid=qid
            )
            task_manager.save()
            # Update task result history
            executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
            TaskResultHistoryDocument.upsert_document(
                task=executed_task, execution_model=execution_manager.to_datamodel()
            )
            execution_manager = execution_manager.update_with_task_manager(task_manager)
            # 未実行タスクのスキップ処理
            task_manager.update_not_executed_tasks_to_skipped(task_type=task_type, qid=qid)
            task_manager.save()
            execution_manager = execution_manager.update_with_task_manager(task_manager)
    finally:
        logger.info("Ending all processes")
    return task_manager


@task
def setup_calibration(
    menu: Menu,
    calib_dir: str,
    execution_id: str,
    qubits: list[str],
    task_names: list[str],
) -> tuple[TaskManager, BaseSession]:
    """Set up calibration environment and initialize required components.

    Args:
    ----
        menu: Menu configuration
        calib_dir: Calibration directory path
        execution_id: Unique execution identifier
        qubits: List of qubit IDs
        task_names: List of task names to execute

    Returns:
    -------
        Tuple containing:
        - Initialized TaskManager
        - Initialized Experiment
        - List of qubit labels

    """
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")

    # Initialize task manager and validate task names
    validated_task_names = validate_task_name(task_names=task_names, username=menu.username)
    task_manager = TaskManager(
        username=menu.username, execution_id=execution_id, qids=qubits, calib_dir=calib_dir
    )

    # Build and save workflow
    task_result = build_workflow(
        task_names=validated_task_names,
        qubits=qubits,
        task_details=menu.task_details,
        backend=menu.backend,
    )
    task_manager.task_result = task_result
    logger.info(f"workflow: {task_manager.task_result}")
    task_manager.save()

    # Determine labels based on task types
    labels: list[str] = []
    if task_manager.has_only_qubit_or_global_tasks(task_names=validated_task_names):
        logger.info("Only qubit or global tasks are present")
        labels = [qid_to_label(q) for q in qubits]
    elif task_manager.has_only_coupling_or_global_tasks(task_names=validated_task_names):
        logger.info("Only coupling or global tasks are present")
        labels = coupling_qids_to_qubit_labels(qids=qubits)
    elif task_manager.has_only_system_tasks(task_names=validated_task_names):
        logger.info("Only system tasks are present")
        labels = []
    else:
        logger.info(f"task names:{validated_task_names}")
        logger.error("this task is not supported")
        error_message = "Invalid task names"
        raise ValueError(error_message)

    # Initialize experiment
    note_path = Path(f"{calib_dir}/calib_note/{task_manager.id}.json")
    initialize()
    session = create_session(
        backend=menu.backend,
        config={"username": menu.username, "qubits": labels, "note_path": note_path},
    )
    session.connect()
    # Update parameters and tasks
    parameters = update_active_output_parameters(username=menu.username, backend=session.name)
    ParameterDocument.insert_parameters(parameters, username=menu.username)
    tasks = update_active_tasks(username=menu.username, backend=session.name)
    logger.info(f"updating tasks: {tasks}")
    TaskDocument.insert_tasks(tasks)

    if session.name == "qubex":
        session.save_note(
            username=menu.username,
            calib_dir=calib_dir,
            execution_id=execution_id,
            task_manager_id=task_manager.id,
        )
        # Initialize ExecutionManager
    ExecutionManager(
        username=menu.username,
        execution_id=execution_id,
        calib_data_path=calib_dir,
    ).reload().update_with_task_manager(task_manager).update_execution_status_to_running()
    logger.info(f"software version: {session.version()}")

    return task_manager, session


@flow(flow_run_name="{qubits}")
def serial_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[str],
    task_names: list[str],
) -> dict[str, bool]:
    """Execute calibration tasks sequentially for a list of qubits.

    This flow initializes the calibration environment and executes tasks one by one
    for each qubit in the provided list.

    Args:
    ----
        menu: Menu configuration containing task details
        calib_dir: Directory for calibration data
        successMap: Dictionary tracking task execution success status
        execution_id: Unique identifier for this execution
        qubits: List of qubit IDs to calibrate
        task_names: List of task names to execute

    Returns:
    -------
        Dictionary mapping task names to their execution success status

    """
    task_manager, session = setup_calibration(
        menu=menu,
        calib_dir=calib_dir,
        execution_id=execution_id,
        qubits=qubits,
        task_names=task_names,
    )

    for qid in qubits:
        task_manager = cal_serial(
            menu=menu,
            session=session,
            task_manager=task_manager,
            task_names=task_names,
            qid=qid,
        )
    return successMap


@flow(flow_run_name="{qubits}")
def batch_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[str],
    task_names: list[str],
) -> dict[str, bool]:
    """Execute calibration tasks in batch mode for a list of qubits.

    This flow initializes the calibration environment and executes tasks in batch mode
    for all qubits simultaneously.

    Args:
    ----
        menu: Menu configuration containing task details
        calib_dir: Directory for calibration data
        successMap: Dictionary tracking task execution success status
        execution_id: Unique identifier for this execution
        qubits: List of qubit IDs to calibrate
        task_names: List of task names to execute

    Returns:
    -------
        Dictionary mapping task names to their execution success status

    """
    task_manager, session = setup_calibration(
        menu=menu,
        calib_dir=calib_dir,
        execution_id=execution_id,
        qubits=qubits,
        task_names=task_names,
    )

    task_manager = cal_batch(
        menu=menu,
        session=session,
        task_manager=task_manager,
        task_names=task_names,
        qids=qubits,
    )
    return successMap


async def dispatch(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    schedule: ScheduleNode,
    task_names: list[str],
) -> None:
    """Dispatch calibration flows based on the schedule configuration.

    This function handles the orchestration of calibration flows according to the
    provided schedule, supporting both serial and parallel execution patterns.

    Args:
    ----
        menu: Menu configuration containing task details
        calib_dir: Directory for calibration data
        successMap: Dictionary tracking task execution success status
        execution_id: Unique identifier for this execution
        schedule: Node defining the execution schedule (Serial/Parallel/Batch)
        task_names: List of task names to execute

    Raises:
    ------
        TypeError: If the schedule type is not supported

    """
    if isinstance(schedule, SerialNode):
        for schedule_node in schedule.serial:
            if isinstance(schedule_node, SerialNode):
                serial_cal_flow(
                    menu=menu,
                    calib_dir=calib_dir,
                    successMap=successMap,
                    execution_id=execution_id,
                    qubits=schedule_node.serial,
                    task_names=task_names,
                )
            if isinstance(schedule_node, BatchNode):
                batch_cal_flow(
                    menu=menu,
                    calib_dir=calib_dir,
                    successMap=successMap,
                    execution_id=execution_id,
                    qubits=schedule_node.batch,
                    task_names=task_names,
                )
            if isinstance(schedule_node, ParallelNode):
                parallel_deployments = []
                for qid in schedule_node.parallel:
                    parameters = {
                        "menu": menu.model_dump(),
                        "calib_dir": calib_dir,
                        "successMap": successMap,
                        "execution_id": execution_id,
                        "qubits": [qid],
                        "task_names": task_names,
                    }
                    parallel_deployments.append(
                        run_deployment(
                            "serial-cal-flow/oqtopus-serial-cal-flow", parameters=parameters
                        )
                    )
                await asyncio.gather(*parallel_deployments)
    elif isinstance(schedule, ParallelNode):
        deployments = []
        for schedule_node in schedule.parallel:
            if isinstance(schedule_node, SerialNode):
                parameters = {
                    "menu": menu.model_dump(),
                    "calib_dir": calib_dir,
                    "successMap": successMap,
                    "execution_id": execution_id,
                    "qubits": schedule_node.serial,
                    "task_names": task_names,
                }
                deployments.append(
                    run_deployment("serial-cal-flow/oqtopus-serial-cal-flow", parameters=parameters)
                )
            if isinstance(schedule_node, BatchNode):
                parameters = {
                    "menu": menu.model_dump(),
                    "calib_dir": calib_dir,
                    "successMap": successMap,
                    "execution_id": execution_id,
                    "qubits": schedule_node.batch,
                    "task_names": task_names,
                }
                deployments.append(
                    run_deployment("batch-cal-flow/oqtopus-batch-cal-flow", parameters=parameters)
                )
        await asyncio.gather(*deployments)
    else:
        raise TypeError(f"Invalid schedule type: {type(schedule)}")


@flow(
    name="dispatch-cal-flow",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
    flow_run_name="{execution_id}",
)
async def dispatch_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    task_names: list[str],
) -> dict[str, bool]:
    """Execute one-qubit calibration tasks based on the provided menu.

    This flow orchestrates the execution of calibration tasks according to the
    provided menu's schedule configuration. It supports various execution patterns
    including serial, parallel, and batch processing.

    Args:
    ----
        menu: Menu configuration containing task details and schedule
        calib_dir: Directory for calibration data
        successMap: Dictionary tracking task execution success status
        execution_id: Unique identifier for this execution
        task_names: List of task names to execute

    Returns:
    -------
        Dictionary mapping task names to their execution success status

    """
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    schedule = menu.schedule
    logger.info(f"schedule: {schedule}")
    logger.info(f"serial type:{isinstance(schedule,SerialNode)}")
    logger.info(f"parallel type:{isinstance(schedule,ParallelNode)}")
    logger.info(f"batch type:{isinstance(schedule,BatchNode)}")
    await dispatch(
        menu, calib_dir, successMap, execution_id, schedule=schedule, task_names=task_names
    )
    return successMap


# ----------------------------------------
# 1. Parallel of Serials
# Run [0 → 1] and [4 → 5] in sequence, both in parallel (unsynchronized)
# → 0→1 and 4→5 are run in serial blocks, and those blocks are run concurrently
# ----------------------------------------
# {
#   "parallel": [
#     { "serial": [0, 1] },
#     { "serial": [4, 5] }
#   ]
# }

# ----------------------------------------
# 2. Parallel of Batches
# Run [0, 1] and [4, 5] as separate batch jobs, both in parallel (unsynchronized)
# → Two batch jobs executed concurrently
# ----------------------------------------
# {
#   "parallel": [
#     { "batch": [0, 1] },
#     { "batch": [4, 5] }
#   ]
# }

# ----------------------------------------
# 3. Parallel of Serial and Batch
# Run [0 → 1] in sequence and [4, 5] as a batch, both in parallel (unsynchronized)
# → Heterogeneous blocks (serial and batch) run concurrently
# ----------------------------------------
# {
#   "parallel": [
#     { "serial": [0, 1] },
#     { "batch": [4, 5] }
#   ]
# }

# ----------------------------------------
# 4. Serial of Serials
# First run [0 → 1] in sequence, then run [4 → 5] in sequence
# → Sequential execution of two serial blocks
# ----------------------------------------
# {
#   "serial": [
#     { "serial": [0, 1] },
#     { "serial": [4, 5] }
#   ]
# }

# ----------------------------------------
# 5. Serial of Batches
# First run [0, 1] as a batch, then run [4, 5] as a batch
# → Sequential execution of two batch jobs
# ----------------------------------------
# {
#   "serial": [
#     { "batch": [0, 1] },
#     { "batch": [4, 5] }
#   ]
# }

# ----------------------------------------
# 6. Serial of Serial and Batch
# First run [0 → 1] in sequence, then run [4, 5] as a batch
# → Run a serial block followed by a batch block
# ----------------------------------------
# {
#   "serial": [
#     { "serial": [0, 1] },
#     { "batch": [4, 5] }
#   ]
# }
