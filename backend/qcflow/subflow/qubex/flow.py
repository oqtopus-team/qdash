from prefect import flow, get_run_logger
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qcflow.subflow.qubex.task import (
    TaskManager,
    TaskResult,
    check_noise_task,
    check_status_task,
    configure_task,
    linkup_task,
    rabi_task,
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
        qubits=[4, 5, 6, 7],
        config_dir="/home/shared/config",
    )
    task_manager = TaskManager()
    dummy_result = TaskResult(name="dummy", status="pending", message="")
    check_status_result = check_status_task.submit(exp, task_manager, dummy_result).result()
    linkup_result = linkup_task.submit(exp, task_manager, check_status_result).result()
    configure_result = configure_task.submit(exp, task_manager, linkup_result).result()
    check_noise_result = check_noise_task.submit(exp, task_manager, configure_result).result()
    rabi_task.submit(exp, task_manager, check_noise_result).result()
    logger.info(f"Final State: {task_manager.model_dump()}")
    return successMap
