from pathlib import Path

import pendulum
from dotenv import load_dotenv
from prefect import flow, get_run_logger, runtime
from qdash.datamodel.menu import MenuModel as Menu
from qdash.neodbmodel.execution_counter import ExecutionCounterDocument
from qdash.neodbmodel.execution_history import ExecutionHistoryDocument
from qdash.neodbmodel.execution_lock import ExecutionLockDocument
from qdash.neodbmodel.initialize import initialize
from qdash.workflow.cal_flow import qubex_one_qubit_cal_flow
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
    exectuion_is_locked = ExecutionLockDocument.get_lock_status()
    if exectuion_is_locked:
        logger.error("Calibration is already running.")
        error_message = "Calibration is already running."
        raise CalibrationRunningError(error_message)
    ExecutionLockDocument.lock()
    execution_id = runtime.flow_run.name
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

    execution_manager = ExecutionManager(
        username=menu.username,
        name=menu.name,
        execution_id=execution_id,
        calib_data_path=calib_dir,
        tags=menu.tags,
        fridge_info={"temperature": 0.0},
        chip_id="SAMPLE",
        note={"qubex_version": get_package_version("qubex"), "ui_url": ui_url},
    ).save()
    ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())
    execution_manager = execution_manager.start_execution().save()
    ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())
    execution_manager = execution_manager.update_execution_status_to_running().save()
    ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())
    try:
        success_map = qubex_one_qubit_cal_flow(menu, calib_dir, success_map, execution_id)
        execution_manager = ExecutionManager.load_from_file(calib_dir).complete_execution()
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
        execution_manager = ExecutionManager.load_from_file(calib_dir).fail_execution()
    finally:
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())
        ExecutionLockDocument.unlock()
