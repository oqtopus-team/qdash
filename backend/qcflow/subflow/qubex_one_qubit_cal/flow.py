import asyncio

from neodbmodel.execution_history import ExecutionHistoryDocument
from prefect import flow, get_run_logger
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qcflow.subflow.execution_manager import ExecutionManager
from qcflow.subflow.task import (
    build_workflow,
    cal_sequence,
    # execute_dynamic_task,
    # task_classes,
    validate_task_name,
)
from qcflow.subflow.task_manager import TaskManager
from qcflow.subflow.util import convert_label, generate_dag, update_active_output_parameters
from qubex.experiment import Experiment
from qubex.version import get_package_version
from repository.initialize import initialize

# @flow(
#     flow_run_name="{qubits}",
# )
# def cal_flow(
#     menu: Menu,
#     calib_dir: str,
#     successMap: dict[str, bool],
#     execution_id: str,
#     qubits: list[str],
# ) -> dict[str, bool]:
#     """Deployment to run calibration flow for a single qubit or a pair of qubits."""
#     logger = get_run_logger()
#     logger.info(f"Menu name: {menu.name}")
#     logger.info(f"Qubex version: {get_package_version('qubex')}")
#     logger.info(f"Qubits: {qubits}")
#     labels = [convert_label(q) for q in qubits]
#     exp = Experiment(
#         chip_id="64Q",
#         qubits=labels,
#         config_dir="/home/shared/config",
#     )
#     exp.note.clear()
#     task_names = validate_task_name(menu.exp_list)
#     task_manager = TaskManager(execution_id=execution_id, qids=qubits, calib_dir=calib_dir)
#     workflow = build_workflow(task_names, qubits=qubits)
#     task_manager.task_result = workflow
#     task_manager.save()
#     em = ExecutionManager.load_from_file(calib_dir).update_with_task_manager(task_manager)
#     initialize()
#     ExecutionHistoryDocument.update_document(em)
#     try:
#         logger.info("Starting all processes")
#         for task_name in task_names:
#             if task_name in task_classes:
#                 task_manager = execute_dynamic_task(
#                     exp=exp,
#                     task_manager=task_manager,
#                     task_name=task_name,
#                 )
#     except Exception as e:
#         logger.error(f"Failed to execute task: {e}")
#     finally:
#         logger.info("Ending all processes")
#     return successMap


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
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    labels = [convert_label(q) for q in qubits]
    exp = Experiment(
        chip_id="64Q",
        qubits=labels,
        config_dir="/home/shared/config",
    )
    exp.note.clear()
    task_names = validate_task_name(menu.exp_list)
    task_manager = TaskManager(execution_id=execution_id, qids=qubits, calib_dir=calib_dir)
    workflow = build_workflow(task_names, qubits=qubits)
    task_manager.task_result = workflow
    task_manager.save()
    generate_dag(f"{calib_dir}/task/{task_manager.id}.json")
    # update_active_output_parameters()
    execution_manager = ExecutionManager.load_from_file(calib_dir).update_with_task_manager(
        task_manager
    )
    initialize()
    ExecutionHistoryDocument.update_document(execution_manager=execution_manager)
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

    results = await asyncio.gather(*deployments)


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
    if len(menu.one_qubit_calib_plan) == 1:
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
