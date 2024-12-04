# import json
import time
from datetime import datetime
from typing import Union

from db.experiment_history import (
    insert_experiment_history,
    update_experiment_history,
)
from dbmodel.one_qubit_calib import Status as NodeStatus
from prefect import flow, get_run_logger, task
from prefect.runner import submit_to_runner, wait_for_submitted_runs
from prefect.runtime import flow_run
from prefect.task_runners import SequentialTaskRunner
from qcflow.db.experiment import put_experiment
from qcflow.db.mongo import update_node_status
from qcflow.schema.menu import Menu, Mode
from qcflow.session.labrad import labrad_session
from qcflow.subflow.one_qubit_calibration.task import (
    check_sideband_all,
    create_instrument_manager,
    execute_experiment,
)

from .experiment import (
    experiment_map,
)
from .util import (
    handle_calibration_result,
    initialize_notes,
    input_params_to_dict,
    send_slack_notification,
    update_slack_failure_notification,
    update_slack_success_notification,
)


def select_mode(menu: Menu) -> list[str] | None:
    exp_list: list[str] | None = menu.exp_list

    if menu.mode not in {
        Mode.DEFAULT.value,
        Mode.PRESET1.value,
        Mode.PRESET2.value,
        Mode.CUSTOM.value,
    }:
        raise ValueError(f"mode: {menu.mode} is not supported")

    if exp_list is None or all(isinstance(item, str) for item in exp_list):
        return exp_list
    else:
        raise ValueError("exp_list must be a list of strings or None")


@task
def start_one_qubit_calibration():
    return "success"


@flow(
    name="one-qubit-calibration-flow",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
    flow_run_name="{execution_id}",
)
def one_qubit_calibration_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
) -> dict[str, bool]:
    logger = get_run_logger()
    logger.info(menu.name)

    for qubit_index_list in menu.one_qubit_calib_plan:
        for qubit_index in qubit_index_list:
            update_node_status(qubit_index, NodeStatus.SCHEDULED)

    success = start_one_qubit_calibration()
    submit_to_runner(
        series_calibration,
        [
            {
                "menu": menu,
                "qubit_index_list": series_block,
                "notes": None,
                "calib_dir": calib_dir,
                "depend": success,
                "execution_id": execution_id,
            }
            for series_block in menu.one_qubit_calib_plan
        ],
    )
    wait_for_submitted_runs()  # type: ignore
    successMap["one-qubit-calibration-flow"] = True
    return successMap


def generate_flow_run_name():
    parameters = flow_run.parameters
    qubit_index_list = parameters["qubit_index_list"]
    id = qubit_index_list[0] // 4
    return f"MUX{id}-Q{qubit_index_list}"


@flow(
    flow_run_name=generate_flow_run_name,
    task_runner=SequentialTaskRunner(),
    log_prints=True,
)
async def series_calibration(
    menu: Menu,
    qubit_index_list: list[int],
    notes: Union[dict, None] = None,
    calib_dir: str = "",
    depend: str = "",
    execution_id: str = "",
):
    logger = get_run_logger()
    depend = "success"
    max_retry = 1
    for qubit_index in qubit_index_list:
        for retry in range(max_retry):
            try:
                depend = single_calibration(
                    menu=menu,
                    qubit_index=qubit_index,
                    notes=notes,
                    calib_dir=calib_dir,
                    depend=depend,
                    execution_id=execution_id,
                )  # type: ignore
            except Exception:
                logger.info(f"Retry {retry} for Q{qubit_index}")
                time.sleep(10)
            else:
                depend = depend
                break


@flow(
    flow_run_name="Q{qubit_index}",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
)
def single_calibration(
    menu: Menu,
    qubit_index: int,
    notes: Union[dict, None] = None,
    calib_dir: str = "",
    depend: str = "",
    execution_id: str = "",
) -> str:
    fig_path = f"{calib_dir}/fig_tdm"
    with labrad_session() as session:
        logger = get_run_logger()
        save = True
        savefig = True
        tdm = create_instrument_manager(menu, session, [qubit_index])
        if notes is None:
            notes = initialize_notes(qubit_index)
            logger.info(f"notes: {notes}")
        result = {
            "success": True,
            "fail_at": "",
        }
        contents, ts = send_slack_notification(menu)
        exp_list = select_mode(menu)
        logger.info(f"exp_list: {menu.model_dump()}")
        prev_status = check_sideband_all(session=session)
        for exp_name in exp_list:
            try:
                logger.info(f"exp : {exp_name}")
                update_node_status(qubit_index, NodeStatus.RUNNING)
                exp = experiment_map[exp_name]
                input_params = exp.__dict__
                input_params = input_params_to_dict(input_params)
                timestamp = datetime.now()
                label = f"Q{qubit_index}"
                insert_experiment_history(
                    label=label,
                    exp_name=exp_name,
                    input_params=input_params,
                    output_params={},
                    fig_path=fig_path,
                    timestamp=timestamp,
                    execution_id=execution_id,
                )
                put_experiment(exp_name)
                status = execute_experiment(
                    exp_name=exp_name,
                    tdm=tdm,
                    exp=experiment_map[exp_name],
                    notes=notes,
                    save=save,
                    savefig=savefig,
                    savepath=fig_path,
                    status=prev_status,
                )  # type: ignore
                if status != "success":
                    update_experiment_history(
                        label=label,
                        exp_name=exp_name,
                        status=status,
                        output_params={},
                        timestamp=timestamp,
                    )
                    raise Exception(f"Error: {status}")

                output_params = {}  # TODO: implement output_params
                update_experiment_history(
                    label=label,
                    exp_name=exp_name,
                    status=status,
                    output_params=output_params,
                    timestamp=timestamp,
                )
                update_slack_success_notification(
                    contents, ts, exp_name, qubit_index, fig_path
                )
                update_node_status(qubit_index, NodeStatus.SUCCESS)
                if status != "success":
                    result["success"] = False
                    result["fail_at"] = exp_name
                    break
                prev_status = status

            except Exception as e:
                update_slack_failure_notification(contents, exp_name, qubit_index)
                update_node_status(qubit_index, NodeStatus.FAILED)
                raise Exception(f"Error: {e}")
        handle_calibration_result(
            notes, qubit_index, status, calib_dir, menu, execution_id
        )
    return "success"
