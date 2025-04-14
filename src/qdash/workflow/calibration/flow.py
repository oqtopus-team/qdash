import asyncio
import json
from pathlib import Path

from prefect import flow, get_run_logger
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
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
def cal_sequence(
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
def cal_sequence_batch(
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
def cal_flow(
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
        task_manager = cal_sequence(
            menu=menu, exp=exp, task_manager=task_manager, task_names=task_names, qid=qid
        )
    return successMap


@flow(
    flow_run_name="{batch_qubits}",
)
def batch_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    batch_qubits: list[list[str]],
    task_names: list[str],
) -> dict[str, bool]:
    """Deployment to run calibration flow for a single qubit or a pair of qubits."""
    qids: list[str]
    qids = [q for sublist in batch_qubits for q in sublist]
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    task_names = validate_task_name(menu.tasks, username=menu.username)
    task_manager = TaskManager(
        username=menu.username, execution_id=execution_id, qids=qids, calib_dir=calib_dir
    )
    task_result = build_workflow(
        task_names=task_names,
        qubits=qids,
        task_details=menu.task_details,
    )
    task_manager.task_result = task_result

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
    logger.info("batch_mode is True")
    for qubits in batch_qubits:
        task_manager = cal_sequence_batch(
            menu=menu, exp=exp, task_manager=task_manager, task_names=task_names, qids=qubits
        )
    return successMap


async def trigger_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[list[str]],
    task_names: list[str],
) -> None:
    """Trigger calibration flow for all qubits."""
    deployments = []
    if menu.batch_mode:
        parameters = {
            "menu": menu.model_dump(),
            "calib_dir": calib_dir,
            "successMap": successMap,
            "execution_id": execution_id,
            "batch_qubits": qubits,
            "task_names": task_names,
        }
        deployments.append(
            run_deployment("batch-cal-flow/oqtopus-batch-cal-flow", parameters=parameters)
        )
    else:
        for qubit in qubits:
            parameters = {
                "menu": menu.model_dump(),
                "calib_dir": calib_dir,
                "successMap": successMap,
                "execution_id": execution_id,
                "qubits": qubit,
                "task_names": task_names,
            }
            deployments.append(run_deployment("cal-flow/oqtopus-cal-flow", parameters=parameters))

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
    plan = menu.qids
    logger.info(f"batch_mode: {menu.batch_mode}")
    logger.info(f"type:{type(menu.batch_mode)}")
    await trigger_cal_flow(menu, calib_dir, successMap, execution_id, plan, task_names=task_names)
    return successMap
