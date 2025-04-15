import asyncio
import json
from pathlib import Path

from prefect import flow, get_run_logger
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
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.parameter import ParameterDocument
from qdash.dbmodel.task import TaskDocument
from qdash.workflow.calibration.task import (
    execute_dynamic_task_batch,
    execute_dynamic_task_by_qid,
    validate_task_name,
)
from qdash.workflow.calibration.util import (
    coupling_qids_to_qubit_labels,
    qid_to_label,
    update_active_output_parameters,
    update_active_tasks,
)
from qdash.workflow.manager.execution import ExecutionManager
from qdash.workflow.manager.task import TaskManager
from qdash.workflow.tasks.active_protocols import generate_task_instances
from qubex.experiment import Experiment
from qubex.version import get_package_version


@flow(name="build-workflow")
def build_workflow(task_names: list[str], qubits: list[str], task_details: dict) -> TaskResultModel:
    """Build workflow."""
    task_result = TaskResultModel()
    global_previous_task_id = ""
    qubit_previous_task_id = {qubit: "" for qubit in qubits}
    coupling_previous_task_id = {qubit: "" for qubit in qubits}
    task_instances = generate_task_instances(task_names=task_names, task_details=task_details)
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
    exp: Experiment,
    task_manager: TaskManager,
    task_names: list[str],
    qid: str,
) -> TaskManager:
    """Calibrate in sequence."""
    logger = get_run_logger()
    try:
        task_instances = generate_task_instances(
            task_names=task_names, task_details=menu.task_details
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
                task_manager = execute_dynamic_task_by_qid(
                    exp=exp,
                    task_manager=task_manager,
                    task_instance=task_instances[task_name],
                    qid=qid,
                )
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
    finally:
        logger.info("Ending all processes")
    return task_manager


@flow(flow_run_name="{qids}")
def cal_batch(
    menu: Menu,
    exp: Experiment,
    task_manager: TaskManager,
    task_names: list[str],
    qids: list[str],
) -> TaskManager:
    """Calibrate in sequence."""
    logger = get_run_logger()
    try:
        task_instances = generate_task_instances(
            task_names=task_names, task_details=menu.task_details
        )
        for task_name in task_names:
            if task_name in task_instances:
                logger.info(f"Starting task: {task_name}")
                task_manager = execute_dynamic_task_batch(
                    exp=exp,
                    task_manager=task_manager,
                    task_instance=task_instances[task_name],
                    qids=qids,
                )
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
    finally:
        logger.info("Ending all processes")
    return task_manager


@flow(
    flow_run_name="{qubits}",
)
def serial_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[str],
    task_names: list[str],
) -> dict[str, bool]:
    """Deployment to run calibration flow for a single qubit or a pair of qubits."""
    qids = qubits
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    task_names = validate_task_name(task_names=task_names, username=menu.username)
    task_manager = TaskManager(
        username=menu.username, execution_id=execution_id, qids=qids, calib_dir=calib_dir
    )
    task_result = build_workflow(
        task_names=task_names,
        qubits=qids,
        task_details=menu.task_details,
    )
    task_manager.task_result = task_result

    logger.info(f"workflow: {task_manager.task_result}")

    task_manager.save()
    if task_manager.has_only_qubit_or_global_tasks(task_names=task_names):
        logger.info("Only qubit or global tasks are present")
        labels = [qid_to_label(q) for q in qids]
    elif task_manager.has_only_coupling_or_global_tasks(task_names=task_names):
        logger.info("Only coupling or global tasks are present")
        labels = coupling_qids_to_qubit_labels(qids=qids)
    elif task_manager.has_only_system_tasks(task_names=task_names):
        logger.info("Only system tasks are present")
        labels = []
        qids = ["system"]
    else:
        logger.info(f"task names:{task_names}")
        logger.error("this task is not supported")
        raise ValueError("Invalid task names")  # noqa: EM101
    # パラメータと設定の更新
    parameters = update_active_output_parameters(username=menu.username)
    ParameterDocument.insert_parameters(parameters)
    tasks = update_active_tasks(username=menu.username)
    logger.info(f"updating tasks: {tasks}")
    TaskDocument.insert_tasks(tasks)

    # ExecutionManagerの初期化と更新

    ExecutionManager(
        username=menu.username,
        execution_id=execution_id,
        calib_data_path=calib_dir,
    ).reload().update_with_task_manager(task_manager).update_execution_status_to_running()

    # キャリブレーションノートの初期化とファイル出力
    note_path = Path(f"{calib_dir}/calib_note/{task_manager.id}.json")
    note_path.parent.mkdir(parents=True, exist_ok=True)

    # チップの最新のマスターノートを取得
    master_doc = (
        CalibrationNoteDocument.find({"task_id": "master"})
        .sort([("timestamp", -1)])  # 更新時刻で降順ソート
        .limit(1)
        .run()
    )

    if not master_doc:
        # マスターノートが存在しない場合は新規作成
        master_doc = CalibrationNoteDocument.upsert_note(
            username=menu.username,
            execution_id=execution_id,
            task_id="master",
            note={},  # 空のノートで初期化
        )
    else:
        master_doc = master_doc[0]  # 最新のドキュメントを取得

    # JSONファイルとして出力
    note_path.write_text(json.dumps(master_doc.note, indent=2))

    initialize()
    # 実験の初期化
    exp = Experiment(
        chip_id="64Q",
        qubits=labels,
        config_dir="/app/config",
        params_dir="/app/config",
        calib_note_path=note_path,
    )
    exp.note.clear()
    for qid in qids:
        task_manager = cal_serial(
            menu=menu, exp=exp, task_manager=task_manager, task_names=task_names, qid=qid
        )
    return successMap


@flow(
    flow_run_name="{qubits}",
)
def batch_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[str],
    task_names: list[str],
) -> dict[str, bool]:
    """Deployment to run calibration flow for a single qubit or a pair of qubits."""
    qids = qubits
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    task_names = validate_task_name(task_names=task_names, username=menu.username)
    task_manager = TaskManager(
        username=menu.username, execution_id=execution_id, qids=qids, calib_dir=calib_dir
    )
    task_result = build_workflow(
        task_names=task_names,
        qubits=qids,
        task_details=menu.task_details,
    )
    task_manager.task_result = task_result

    logger.info(f"workflow: {task_manager.task_result}")

    task_manager.save()
    if task_manager.has_only_qubit_or_global_tasks(task_names=task_names):
        logger.info("Only qubit or global tasks are present")
        labels = [qid_to_label(q) for q in qids]
    elif task_manager.has_only_coupling_or_global_tasks(task_names=task_names):
        logger.info("Only coupling or global tasks are present")
        labels = coupling_qids_to_qubit_labels(qids=qids)
    elif task_manager.has_only_system_tasks(task_names=task_names):
        logger.info("Only system tasks are present")
        labels = []
        qids = ["system"]
    else:
        logger.info(f"task names:{task_names}")
        logger.error("this task is not supported")
        raise ValueError("Invalid task names")  # noqa: EM101
    # パラメータと設定の更新
    parameters = update_active_output_parameters(username=menu.username)
    ParameterDocument.insert_parameters(parameters)
    tasks = update_active_tasks(username=menu.username)
    logger.info(f"updating tasks: {tasks}")
    TaskDocument.insert_tasks(tasks)

    # ExecutionManagerの初期化と更新

    ExecutionManager(
        username=menu.username,
        execution_id=execution_id,
        calib_data_path=calib_dir,
    ).reload().update_with_task_manager(task_manager).update_execution_status_to_running()

    # キャリブレーションノートの初期化とファイル出力
    note_path = Path(f"{calib_dir}/calib_note/{task_manager.id}.json")
    note_path.parent.mkdir(parents=True, exist_ok=True)

    # チップの最新のマスターノートを取得
    master_doc = (
        CalibrationNoteDocument.find({"task_id": "master"})
        .sort([("timestamp", -1)])  # 更新時刻で降順ソート
        .limit(1)
        .run()
    )

    if not master_doc:
        # マスターノートが存在しない場合は新規作成
        master_doc = CalibrationNoteDocument.upsert_note(
            username=menu.username,
            execution_id=execution_id,
            task_id="master",
            note={},  # 空のノートで初期化
        )
    else:
        master_doc = master_doc[0]  # 最新のドキュメントを取得

    # JSONファイルとして出力
    note_path.write_text(json.dumps(master_doc.note, indent=2))

    initialize()
    # 実験の初期化
    exp = Experiment(
        chip_id="64Q",
        qubits=labels,
        config_dir="/app/config",
        params_dir="/app/config",
        calib_note_path=note_path,
    )
    exp.note.clear()
    task_manager = cal_batch(
        menu=menu, exp=exp, task_manager=task_manager, task_names=task_names, qids=qids
    )
    return successMap


async def trigger_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    schedule: ScheduleNode,
    task_names: list[str],
) -> None:
    """Trigger calibration flow for all qubits."""
    deployments = []
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
    elif isinstance(schedule, ParallelNode):
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
    else:
        raise TypeError(f"Invalid schedule type: {type(schedule)}")

    await asyncio.gather(*deployments)


@flow(
    name="qubex-one-qubit-cal-flow",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
    flow_run_name="{execution_id}",
)
async def qubex_one_qubit_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    task_names: list[str],
) -> dict[str, bool]:
    """Flow to calibrate one qubit or a pair of qubits."""
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    schedule = menu.schedule
    logger.info(f"schedule: {schedule}")
    logger.info(f"seirial type:{isinstance(schedule,SerialNode)}")
    logger.info(f"parallel type:{isinstance(schedule,ParallelNode)}")
    logger.info(f"batch type:{isinstance(schedule,BatchNode)}")
    await trigger_cal_flow(
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
