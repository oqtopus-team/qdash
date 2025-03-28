from pathlib import Path

import pendulum
from dotenv import load_dotenv
from prefect import flow, get_run_logger, runtime
from qdash.datamodel.menu import MenuModel as Menu
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.calibration.flow import qubex_one_qubit_cal_flow
from qdash.workflow.integration.config_downloader import update_config
from qdash.workflow.manager.execution import ExecutionManager
from qdash.workflow.utiltask.create_directory import (
    create_directory_task,
)
from qubex.version import get_package_version


class CalibrationRunningError(Exception):
    """Exception raised when calibration is already running."""


calibration_flow_map = {
    "qubex-one-qubit-cal-flow": qubex_one_qubit_cal_flow,
}


initialize()
load_dotenv(verbose=True)
dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path)


def generate_execution_id() -> str:
    """Generate a unique execution ID based on the current date and an execution index. e.g. 20220101-001.

    Returns
    -------
        str: The generated execution ID.

    """
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    execution_index = ExecutionCounterDocument.get_next_index(date_str)
    return f"{date_str}-{execution_index:03d}"


@flow(name="main", log_prints=True, flow_run_name="{execution_id}")
def main_flow(
    menu: Menu,
    execution_id: str | None = None,
) -> None:
    """Execute the calibration process.

    Parameters
    ----------
    menu : Menu
        The menu object containing the flow configuration.

    execution_id : str
        The execution ID.

    Raises
    ------
    CalibrationRunningError
        If calibration is already running.
    ValueError
        If execution ID is None.

    """
    logger = get_run_logger()
    if execution_id is None:
        execution_id = generate_execution_id()
    ui_url = runtime.flow_run.get_flow_run_ui_url()
    if ui_url:
        # Replace both 127.0.0.1 and prefect-server with localhost
        ui_url = ui_url.replace("127.0.0.1", "localhost").replace("prefect-server", "localhost")
    logger.info(f"Execution ID: {execution_id}")
    exectuion_is_locked = ExecutionLockDocument.get_lock_status()
    commit_id = update_config().result()
    if exectuion_is_locked:
        logger.error("Calibration is already running.")
        error_message = "Calibration is already running."
        raise CalibrationRunningError(error_message)
    ExecutionLockDocument.lock()
    if execution_id:
        date_str, index = execution_id.split("-")
    else:
        logger.error("Execution ID is None.")
        error_message = "Execution ID is None."
        raise ValueError(error_message)
    calib_dir = f"/app/calib_data/{menu.username}/{date_str}/{index}"
    create_directory_task.submit(calib_dir).result()
    latest_calib_dir = f"/app/calib_data/{menu.username}/{date_str}/latest"
    create_directory_task.submit(latest_calib_dir).result()
    success_map = {flow_name: False for flow_name in calibration_flow_map}
    chip_id = ChipDocument.get_current_chip(username=menu.username).chip_id
    execution_manager = (
        ExecutionManager(
            username=menu.username,
            name=menu.name,
            execution_id=execution_id,
            calib_data_path=calib_dir,
            tags=menu.tags,
            fridge_info={"temperature": 0.0},
            chip_id=chip_id,
            note={
                "qubex_version": get_package_version("qubex"),
                "ui_url": ui_url,
                "config_commit_id": commit_id,
            },
        )
        .save()
        .start_execution()
        .update_execution_status_to_running()
    )
    try:
        success_map = qubex_one_qubit_cal_flow(menu, calib_dir, success_map, execution_id)
        execution_manager = execution_manager.reload().complete_execution()
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
        execution_manager = execution_manager.reload().fail_execution()
    finally:
        ExecutionLockDocument.unlock()
