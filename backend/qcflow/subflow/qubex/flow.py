import asyncio

from prefect import flow, get_run_logger
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qcflow.subflow.qubex.task import (
    execute_dynamic_task,
    task_classes,
    validate_task_name,
)
from qubex.experiment import Experiment
from qubex.version import get_package_version
from subflow.qubex.manager import ExecutionManager, TaskResult, TaskStatus


@flow(
    flow_run_name="{sub_index}-{qubits}",
)
def cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[int],
    sub_index: int = 0,
) -> dict[str, bool]:
    """deployment to run calibration flow for a single qubit"""
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    logger.info(f"Qubits: {qubits}")
    exp = Experiment(
        chip_id="64Q",
        qubits=qubits,
        config_dir="/home/shared/config",
    )
    exp.note.clear()
    task_names = validate_task_name(menu.exp_list)
    execution_manager = ExecutionManager(
        execution_id=execution_id,
        calib_data_path=calib_dir,
        task_names=task_names,
        tags=menu.tags,
        qubex_version=get_package_version("qubex"),
        fridge_temperature=0.0,
        chip_id="SAMPLE",
        sub_index=sub_index,
    )
    prev_result = TaskResult(
        name="dummy", upstream_task="", status=TaskStatus.SCHEDULED, message=""
    )
    try:
        logger.info("Starting all processes")
        execution_manager.start_execution()
        execution_manager.update_execution_status_to_running()
        for task_name in execution_manager.tasks.keys():
            if task_name in task_classes:
                prev_result = execute_dynamic_task(
                    exp=exp,
                    execution_manager=execution_manager,
                    task_name=task_name,
                    prev_result=prev_result,
                )
                # execution_manager.save_task_history(task_name)
        execution_manager.update_execution_status_to_success()
        # execution_manager.save_execution_history()
        # execution_manager.save_task_histories()

    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
        execution_manager.update_execution_status_to_failed()
    finally:
        logger.info("Ending all processes")
        execution_manager.end_execution()
    return successMap


async def trigger_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[list[int]],
):
    """Trigger calibration flow for all qubits"""
    deployments = []
    for index, qubit in enumerate(qubits):
        parameters = {
            "menu": menu.model_dump(),
            "calib_dir": calib_dir,
            "successMap": successMap,
            "execution_id": execution_id,
            "qubits": qubit,
            "sub_index": index,
        }
        deployments.append(run_deployment("cal-flow/oqtopus-cal-flow", parameters=parameters))

    results = await asyncio.gather(*deployments)

    print("All Qubits Completed:")
    for result in results:
        print(result)


def organize_qubits(qubits: list[list[int]], parallel: bool) -> list[list[int]]:
    if parallel:
        return qubits
    else:
        # Flatten the list into a single list and return as a single sublist
        merged_qubits = [q for sublist in qubits for q in sublist]
        return [merged_qubits]


@flow(
    name="qubex-flow",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
    flow_run_name="{execution_id}",
)
async def qubex_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
) -> dict[str, bool]:
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    parallel = True
    if parallel:
        logger.info("parallel is True")
        qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        await trigger_cal_flow(menu, calib_dir, successMap, execution_id, qubits)
        return successMap
    else:
        qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        logger.info("parallel is False")
        await trigger_cal_flow(menu, calib_dir, successMap, execution_id, qubits)
        return successMap
