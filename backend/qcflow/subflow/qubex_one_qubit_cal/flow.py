import asyncio
from datetime import datetime

from prefect import flow, get_run_logger, task
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.task import (
    build_workflow,
    execute_dynamic_task,
    task_classes,
    validate_task_name,
)
from qcflow.subflow.task_manager import TaskManager
from qcflow.subflow.util import convert_label

# from qcflow.subflow.task_manager import TaskManager, TaskResult, TaskStatus
from qubex.experiment import Experiment
from qubex.version import get_package_version


@flow(
    flow_run_name="{sub_index}-{qubits}",
)
def cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[str],
    sub_index: int = 0,
) -> dict[str, bool]:
    """deployment to run calibration flow for a single qubit"""
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    logger.info(f"Qubits: {qubits}")
    qubits = [convert_label(q) for q in qubits]
    exp = Experiment(
        chip_id="64Q",
        qubits=qubits,
        config_dir="/home/shared/config",
    )
    exp.note.clear()
    task_names = validate_task_name(menu.exp_list)
    task_manager = TaskManager(qids=["28", "29"], calib_dir=calib_dir)
    workflow = build_workflow(task_names, ["28", "29"])
    task_manager.task_result = workflow
    task_manager.save()
    # task_manager.update_task_status_to_running("CheckStatus",)
    # task_manager.put_input_parameters(
    #     "CreateDRAGHPIPulse", {"test": 1.0}, task_type="qubit", qid="28"
    # )
    # task_manager.put_calib_data(qid="28", task_type="qubit", parameter_name="test", value=1.0)
    # task_manager.export_json(calib_dir=calib_dir)
    try:
        logger.info("Starting all processes")
        for task_name in task_names:
            if task_name in task_classes:
                task_manager = execute_dynamic_task(
                    exp=exp,
                    task_manager=task_manager,
                    task_name=task_name,
                )
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
    finally:
        logger.info("Ending all processes")
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
    execution_manager: ExecutionManager,
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[list[str]],
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

    ## implement gather_results

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
    execution_manager: ExecutionManager,
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
) -> dict[str, bool]:
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    parallel = True
    plan = [["28", "29"]]
    if len(menu.one_qubit_calib_plan) == 1:
        parallel = False
    if parallel:
        logger.info("parallel is True")
        # qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        await trigger_cal_flow(execution_manager, menu, calib_dir, successMap, execution_id, plan)
        merge_results_qubits(calib_dir)
        return successMap
    else:
        # qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        logger.info("parallel is False")
        await trigger_cal_flow(execution_manager, menu, calib_dir, successMap, execution_id, plan)
        merge_results_qubits(calib_dir)
        return successMap


# qubit_calib_plan = [["28", "29"]]
# coupling_calib_plan = [["28-29"]]
