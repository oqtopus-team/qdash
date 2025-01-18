from prefect import flow, get_run_logger
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
    name="qubex-flow",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
    flow_run_name="{execution_id}",
)
def qubex_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
) -> dict[str, bool]:
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    exp = Experiment(
        chip_id="64Q",
        qubits=[21],
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
                execution_manager.save_task_history(task_name)
        execution_manager.update_execution_status_to_success()
        execution_manager.save_execution_history()
        execution_manager.save_task_histories()

    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
        execution_manager.update_execution_status_to_failed(f"Failed to execute task: {e}")
    finally:
        logger.info("Ending all processes")
        execution_manager.end_execution()
    return successMap
