import asyncio

from cal_task import (
    build_workflow,
    execute_dynamic_task_by_qid,
    # execute_dynamic_task,
    # task_classes,
    validate_task_name,
)
from cal_util import qid_to_label, update_active_output_parameters, update_active_tasks
from datamodel.menu import MenuModel as Menu
from neodbmodel.execution_history import ExecutionHistoryDocument
from neodbmodel.initialize import initialize
from neodbmodel.parameter import ParameterDocument
from neodbmodel.task import TaskDocument
from prefect import flow, get_run_logger
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from protocols.active_protocols import task_classes
from qcflow.manager.execution import ExecutionManager
from qcflow.manager.task import TaskManager
from qubex.experiment import Experiment
from qubex.version import get_package_version


@flow(flow_run_name="{qid}")
def cal_sequence(
    exp: Experiment,
    task_manager: TaskManager,
    task_names: list[str],
    qid: str,
) -> TaskManager:
    """Calibrate in sequence."""
    logger = get_run_logger()
    try:
        for task_name in task_names:
            if task_name in task_classes:
                task_type = task_classes[task_name].get_task_type()
                if task_manager.this_task_is_completed(
                    task_name=task_name, task_type=task_type, qid=qid
                ):
                    logger.info(f"Task {task_name} is already completed")
                    continue
                logger.info(f"Starting task: {task_name}")
                task_manager = execute_dynamic_task_by_qid(
                    exp=exp, task_manager=task_manager, task_name=task_name, qid=qid
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
) -> dict[str, bool]:
    """Deployment to run calibration flow for a single qubit or a pair of qubits."""
    username = "admin"
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    labels = [qid_to_label(q) for q in qubits]
    exp = Experiment(
        chip_id="64Q",
        qubits=labels,
        config_dir="/home/shared/config",
    )
    exp.note.clear()
    task_names = validate_task_name(menu.tasks)
    task_manager = TaskManager(
        username=username, execution_id=execution_id, qids=qubits, calib_dir=calib_dir
    )
    task_manager = build_workflow(task_manager=task_manager, task_names=task_names, qubits=qubits)
    task_manager.save()
    parameters = update_active_output_parameters(username=username)
    ParameterDocument.insert_parameters(parameters)
    tasks = update_active_tasks(username=username)
    logger.info(f"updating tasks: {tasks}")
    TaskDocument.insert_tasks(tasks)
    execution_manager = ExecutionManager.load_from_file(calib_dir).update_with_task_manager(
        task_manager
    )
    execution_manager.update_execution_status_to_running()
    initialize()
    ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())
    for qid in qubits:
        task_manager = cal_sequence(exp, task_manager, task_names, qid)
    return successMap


async def trigger_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[list[str]],
) -> None:
    """Trigger calibration flow for all qubits."""
    deployments = []
    for qubit in qubits:
        parameters = {
            "menu": menu.model_dump(),
            "calib_dir": calib_dir,
            "successMap": successMap,
            "execution_id": execution_id,
            "qubits": qubit,
        }
        deployments.append(run_deployment("cal-flow/oqtopus-cal-flow", parameters=parameters))

    await asyncio.gather(*deployments)


def organize_qubits(qubits: list[list[int]], parallel: bool) -> list[list[int]]:
    """Organize qubits into a list of sublists."""
    if parallel:
        return qubits
    else:
        # Flatten the list into a single list and return as a single sublist
        merged_qubits = [q for sublist in qubits for q in sublist]
        return [merged_qubits]


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
) -> dict[str, bool]:
    """Flow to calibrate one qubit or a pair of qubits."""
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    parallel = True
    plan = [["28", "29", "30", "31"]]
    if len(menu.qids) == 1:
        parallel = False
    if parallel:
        logger.info("parallel is True")
        # qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        await trigger_cal_flow(menu, calib_dir, successMap, execution_id, plan)
        return successMap
    else:
        # qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        logger.info("parallel is False")
        await trigger_cal_flow(menu, calib_dir, successMap, execution_id, plan)
        return successMap


# qubit_calib_plan = [["28", "29"]]
# coupling_calib_plan = [["28-29"]]
