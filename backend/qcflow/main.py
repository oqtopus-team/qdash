from pathlib import Path

import pendulum
from cal_flow import qubex_one_qubit_cal_flow
from db.execution_lock import (
    get_execution_lock,
    lock_execution,
    unlock_execution,
)
from dotenv import load_dotenv
from neodbmodel.execution_history import ExecutionHistoryDocument
from neodbmodel.initialize import initialize
from prefect import flow, get_run_logger, runtime
from qcflow.db.bluefors import get_latest_temperature
from qcflow.db.execution_run import get_next_execution_index
from qcflow.db.execution_run_history import insert_execution_run
from qcflow.manager.execution import ExecutionManager
from qcflow.schema.menu import Menu
from qcflow.utiltask.create_directory import (
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
    execution_index = get_next_execution_index(date_str)
    if execution_index is None:
        execution_index = 1  # Default to 1 if None is returned
    return f"{date_str}-{execution_index:03d}"


@flow(name="main", log_prints=True, flow_run_name=generate_execution_id)
def main_flow(
    menu: Menu,
) -> None:
    """Execute the calibration process.

    Parameters
    ----------
    menu : Menu
        The menu object containing the flow configuration.

    Raises
    ------
    CalibrationRunningError
        If calibration is already running.
    ValueError
        If execution ID is None.

    """
    logger = get_run_logger()
    execution_id = runtime.flow_run.get_flow_name()
    ui_url = runtime.flow_run.get_flow_run_ui_url()
    if ui_url:
        ui_url = ui_url.replace("172.22.0.5", "localhost")
    logger.info(f"Execution ID: {execution_id}")
    if get_execution_lock():
        logger.error("Calibration is already running.")
        error_message = "Calibration is already running."
        raise CalibrationRunningError(error_message)
    lock_execution()
    execution_id = runtime.flow_run.name
    if execution_id:
        date_str, index = execution_id.split("-")
    else:
        logger.error("Execution ID is None.")
        error_message = "Execution ID is None."
        raise ValueError(error_message)
    insert_execution_run(
        date_str,
        execution_id,
        menu.model_dump(),
        get_latest_temperature(device_id="XLD", channel_nr=6),
        flow_url=ui_url,
    )
    calib_dir = f"/app/calib_data/{date_str}/{index}"
    create_directory_task.submit(calib_dir).result()
    latest_calib_dir = f"/app/calib_data/{date_str}/latest"
    create_directory_task.submit(latest_calib_dir).result()
    success_map = {flow_name: False for flow_name in menu.flow}

    execution_manager = ExecutionManager(
        name=menu.name,
        execution_id=execution_id,
        calib_data_path=calib_dir,
        tags=menu.tags,
        fridge_info={"temperature": 0.0},
        chip_id="SAMPLE",
        note={"qubex_version": get_package_version("qubex")},
    )
    execution_manager.save()
    ExecutionHistoryDocument.insert_document(execution_manager)
    execution_manager.start_execution()
    execution_manager.update_execution_status_to_running()
    try:
        for flow_name in menu.flow:
            success_map = calibration_flow_map[flow_name](
                menu, calib_dir, success_map, execution_id
            )
        execution_manager.update_execution_status_to_success()
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
        execution_manager.update_execution_status_to_failed()
    finally:
        execution_manager.end_execution()
        unlock_execution()
