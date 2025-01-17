from prefect import flow, get_run_logger
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qcflow.subflow.qubex.task import (
    TaskManager,
    TaskResult,
    execute_dynamic_task,
    task_functions,
)
from qubex.experiment import Experiment


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
    logger.info("Starting qubex_flow")
    exp = Experiment(
        chip_id="64Q",
        qubits=[21],
        config_dir="/home/shared/config",
    )
    exp.note.clear()
    task_manager = TaskManager(
        execution_id=execution_id,
        calib_data_path=calib_dir,
        task_names=menu.exp_list,
        tags=menu.tags,
    )
    prev_result = TaskResult(name="dummy", upstream_task="", status="success", message="")
    for task_name in task_manager.tasks.keys():
        if task_name in task_functions:
            prev_result = execute_dynamic_task(
                exp=exp,
                task_manager=task_manager,
                task_name=task_name,
                prev_result=prev_result,
            )

    logger.info(f"Final Task States: {task_manager.tasks}")
    logger.info(f"Final State: {task_manager.model_dump()}")
    return successMap
