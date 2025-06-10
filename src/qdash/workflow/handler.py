import json
import os
from pathlib import Path

import pendulum
from dotenv import load_dotenv
from prefect import flow, get_run_logger, runtime
from qdash.config import get_settings
from qdash.datamodel.menu import MenuModel as Menu
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.calibration.flow import qubex_one_qubit_cal_flow
from qdash.workflow.integration.config_downloader import update_config
from qdash.workflow.manager.execution import ExecutionManager
from qdash.workflow.utils.slack import SlackContents, Status
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


def generate_execution_id(username: str, chip_id: str) -> str:
    """Generate a unique execution ID based on the current date and an execution index. e.g. 20220101-001.

    Args:
    ----
        username: The username to generate the execution ID for
        chip_id: The chip ID to generate the execution ID for

    Returns:
    -------
        str: The generated execution ID.

    """
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    execution_index = ExecutionCounterDocument.get_next_index(date_str, username, chip_id)
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
    settings = get_settings()
    logger.info(f"notify_bool: {menu.notify_bool}")

    if execution_id is None:
        execution_id = generate_execution_id(menu.username, menu.chip_id)
    if menu.notify_bool:
        slack = SlackContents(
            status=Status.RUNNING,
            title=f"🏃‍♂️ RUNNING {menu.name}...",
            msg="RUNNING",
            ts="",
            path="",
            header=f"{menu.name}: http://localhost:{settings.ui_port}/execution/64Q/{execution_id}",
            channel=settings.slack_channel_id,
            token=settings.slack_bot_token,
        )
        parent_ts = slack.send_slack()
    ui_url = runtime.flow_run.get_flow_run_ui_url()
    if ui_url:
        # Replace both 127.0.0.1 and prefect-server with localhost
        ui_url = ui_url.replace("127.0.0.1", "localhost").replace("prefect-server", "localhost")
    logger.info(f"Execution ID: {execution_id}")
    exectuion_is_locked = ExecutionLockDocument.get_lock_status()
    commit_id = "local" if os.getenv("CONFIG_REPO_URL") == "" else update_config()
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
    calib_note_dir = f"/app/calib_data/{menu.username}/.calibration"
    create_directory_task.submit(calib_note_dir).result()
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
            chip_id=menu.chip_id,
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
    logger.info(f"tasks: {menu.tasks}")
    if "CheckSkew" in menu.tasks:
        logger.info("CheckSkew is in the tasks.")
        success_map = qubex_one_qubit_cal_flow(
            menu, calib_dir, success_map, execution_id, task_names=["CheckSkew"]
        )
        execution_manager = execution_manager.reload()
        logger.info(f"execution manager: {execution_manager.task_results}")
        data = execution_manager.task_results
        model = list(data.values())[0]
        logger.info(f"model: {model}")
        for task in model.system_tasks:
            if task.name == "CheckSkew":
                fig_path = task.figure_path[0]
                logger.info(f"fig_path: {fig_path}")
                if menu.notify_bool:
                    new = SlackContents(
                        status=Status.SUCCESS,
                        title=f"📈 {menu.name} Result",
                        msg="SUCCESS",
                        ts="",
                        path=fig_path,
                        channel=settings.slack_channel_id,
                        token=settings.slack_bot_token,
                    )
                    new.send_slack()
        menu.tasks.remove("CheckSkew")
    try:
        if len(menu.tasks) != 0:
            success_map = qubex_one_qubit_cal_flow(
                menu, calib_dir, success_map, execution_id, task_names=menu.tasks
            )
        execution_manager = execution_manager.reload().complete_execution()
        # Update ChipDocument and ChipHistoryDocument
        chip_doc = ChipDocument.get_current_chip(username=menu.username)
        ChipHistoryDocument.create_history(chip_doc)
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
        execution_manager = execution_manager.reload().fail_execution()
        if menu.notify_bool:
            slack.update_contents(
                status=Status.FAILURE,
                title="Calibration Failed",
                msg="Calibration failed.",
                ts=parent_ts,
                broadcast=True,
            )
            slack.send_slack()
        raise RuntimeError(f"Failed to execute task: {e}") from e
    finally:
        ExecutionLockDocument.unlock()
        latest = (
            CalibrationNoteDocument.find({"task_id": "master"})
            .sort([("timestamp", -1)])  # 更新時刻で降順ソート
            .limit(1)
            .run()
        )[0]
        calib_note = latest.note
        calib_note_path = f"{calib_note_dir}/{chip_id}.json"
        with Path(calib_note_path).open("w", encoding="utf-8") as f:
            json.dump(calib_note, f, indent=4, ensure_ascii=False)
        if menu.notify_bool:
            slack.update_contents(
                status=Status.SUCCESS if success_map else Status.FAILURE,
                title="✅ Calibration finished.",
                msg="SUCCESS",
                ts=parent_ts,
                broadcast=True,
            )
            logger.info(f"exection manager: {execution_manager}")
            slack.send_slack()
            slack.update_contents(
                status=Status.SUCCESS if success_map else Status.FAILURE,
                title="📄 the calibration result is attached.",
                msg="SUCCESS",
                ts=parent_ts,
                path=calib_note_path,
                broadcast=False,
            )
            slack.send_slack()
