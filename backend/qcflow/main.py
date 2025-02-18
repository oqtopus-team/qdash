import datetime
from os.path import dirname, join

from db.execution_lock import (
    get_execution_lock,
    lock_execution,
    unlock_execution,
)
from dotenv import load_dotenv
from prefect import flow, get_run_logger, runtime
from qcflow.db.bluefors import get_latest_temperature
from qcflow.db.execution_run import get_next_execution_index
from qcflow.db.execution_run_history import insert_execution_run
from qcflow.schema.menu import Menu
from qcflow.subflow.execution_manager import ExecutionManager
from qcflow.subflow.qubex_one_qubit_cal.flow import qubex_one_qubit_cal_flow
from qcflow.utiltask.create_directory import (
    create_directory_task,
)
from qubex.version import get_package_version

calibration_flow_map = {
    "qubex-one-qubit-cal-flow": qubex_one_qubit_cal_flow,
}

load_dotenv(verbose=True)
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)


def generate_execution_id():
    date_str = datetime.date.today().strftime("%Y%m%d")
    execution_index = get_next_execution_index(date_str)
    execution_id = f"{date_str}-{execution_index:03d}"
    return execution_id


@flow(name="main", log_prints=True, flow_run_name=generate_execution_id)
def main_flow(
    menu: Menu,
):
    logger = get_run_logger()
    execution_id = runtime.flow_run.get_flow_name()
    ui_url = runtime.flow_run.get_flow_run_ui_url()
    if ui_url:
        ui_url = ui_url.replace("172.22.0.5", "localhost")
    logger.info(f"UI URL: {ui_url}")
    logger.info(f"Execution ID: {execution_id}")
    if get_execution_lock():
        logger.error("Calibration is already running.")
        raise Exception("Calibration is already running.")
    lock_execution()
    execution_id = runtime.flow_run.name
    if execution_id:
        date_str, index = execution_id.split("-")
    else:
        logger.error("Execution ID is None.")
        raise ValueError("Execution ID is None.")
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
    successMap = {flow_name: False for flow_name in menu.flow}
    execution_manager = ExecutionManager(
        execution_id=execution_id,
        calib_data_path=calib_dir,
        tags=menu.tags,
        qubex_version=get_package_version("qubex"),
        fridge_info={"temperature": 0.0},
        chip_id="SAMPLE",
    )
    execution_manager.start_execution()
    execution_manager.update_execution_status_to_running()
    try:
        for flow_name in menu.flow:
            successMap = calibration_flow_map[flow_name](
                execution_manager, menu, calib_dir, successMap, execution_id
            )  # type: ignore
        execution_manager.update_execution_status_to_success()
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
        execution_manager.update_execution_status_to_failed()
    finally:
        execution_manager.end_execution()
        unlock_execution()
