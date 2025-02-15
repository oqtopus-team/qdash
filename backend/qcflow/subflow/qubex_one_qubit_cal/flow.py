import asyncio
from datetime import datetime

from prefect import flow, get_run_logger, task
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qcflow.subflow.task import (
    execute_dynamic_task,
    task_classes,
    validate_task_name,
)
from qubex.experiment import Experiment
from qubex.version import get_package_version
from subflow.manager import ExecutionManager, TaskResult, TaskStatus


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


@task(name="merge-results-qubits")
def merge_results_qubits(calib_dir):
    """Merge results from multiple qubits into calib.json with structure {"qubits": { ... } }.
    If calib.json exists, append new data to the existing qubits."""
    import glob
    import json
    import os

    logger = get_run_logger()
    logger.info(f"Calibration directory: {calib_dir}")

    # Q??.json ファイルを再帰的に検索
    pattern = os.path.join(calib_dir, "**", "Q??.json")
    q_files = glob.glob(pattern, recursive=True)
    for file_path in q_files:
        logger.info(f"File: {file_path}")

    calib_json_path = os.path.join(calib_dir, "calib.json")
    # calib.json が存在する場合は読み込み、存在しなければ初期化
    if os.path.exists(calib_json_path):
        with open(calib_json_path, "r", encoding="utf-8") as f:
            merged_data = json.load(f)
        if "qubits" not in merged_data:
            merged_data["qubits"] = {}
    else:
        merged_data = {"qubits": {}}

    # 各ファイルの内容を、ファイル名（拡張子除く）をキーとして追加
    for file_path in q_files:
        qubit_key = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged_data["qubits"][qubit_key] = data

    # 結果を calib.json に上書き保存
    merged_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    merged_data["couplings"] = {}
    with open(calib_json_path, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)
    logger.info(f"Merged JSON saved to: {calib_json_path}")


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
    name="qubex-one-qubit-cal-flow",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
    flow_run_name="{execution_id}",
)
async def qubex_one_qubit_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
) -> dict[str, bool]:
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    parallel = True
    if len(menu.one_qubit_calib_plan) == 1:
        parallel = False
    if parallel:
        logger.info("parallel is True")
        qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        await trigger_cal_flow(menu, calib_dir, successMap, execution_id, qubits)
        merge_results_qubits(calib_dir)
        return successMap
    else:
        qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        logger.info("parallel is False")
        await trigger_cal_flow(menu, calib_dir, successMap, execution_id, qubits)
        merge_results_qubits(calib_dir)
        return successMap
