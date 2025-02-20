import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from neodbmodel.execution_history import ExecutionHistoryDocument
from prefect import flow, get_run_logger, task
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qcflow.subflow.execution_manager import ExecutionManager
from qcflow.subflow.task import (
    build_workflow,
    execute_dynamic_task,
    task_classes,
    validate_task_name,
)
from qcflow.subflow.task_manager import TaskManager
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment
from qubex.version import get_package_version
from repository.initialize import initialize


@flow(
    flow_run_name="{qubits}",
)
def cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[str],
) -> dict[str, bool]:
    """Deployment to run calibration flow for a single qubit or a pair of qubits."""
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    logger.info(f"Qubits: {qubits}")
    labels = [convert_label(q) for q in qubits]
    exp = Experiment(
        chip_id="64Q",
        qubits=labels,
        config_dir="/home/shared/config",
    )
    exp.note.clear()
    task_names = validate_task_name(menu.exp_list)
    task_manager = TaskManager(execution_id=execution_id, qids=qubits, calib_dir=calib_dir)
    workflow = build_workflow(task_names, qubits=qubits)
    task_manager.task_result = workflow
    task_manager.save()
    em = ExecutionManager.load_from_file(calib_dir).update_with_task_manager(task_manager)
    initialize()
    ExecutionHistoryDocument.update_document(em)
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
def merge_results_qubits(calib_dir: str) -> None:
    """Merge results from multiple qubits into calib.json with structure {"qubits": { ... } }.

    If calib.json exists, append new data to the existing qubits.
    """
    logger = get_run_logger()
    logger.info(f"Calibration directory: {calib_dir}")

    # Q??.json ファイルを再帰的に検索
    # pattern = Path(calib_dir) / "**" / "Q??.json"
    q_files = Path(calib_dir).rglob("Q??.json")
    for file_path in q_files:
        logger.info(f"File: {file_path}")

    calib_json_path = Path(calib_dir) / "calib.json"
    if calib_json_path.exists():
        with calib_json_path.open(encoding="utf-8") as f:
            merged_data = json.load(f)
        if "qubits" not in merged_data:
            merged_data["qubits"] = {}
    else:
        merged_data = {"qubits": {}}
    for file_path in q_files:
        qubit_key = Path(file_path).stem
        with Path(file_path).open(encoding="utf-8") as f:
            data = json.load(f)
        merged_data["qubits"][qubit_key] = data

    merged_data["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    merged_data["couplings"] = {}
    with calib_json_path.open("w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)
    logger.info(f"Merged JSON saved to: {calib_json_path}")


async def trigger_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
    qubits: list[list[str]],
) -> None:
    """Trigger calibration flow for all qubits."""
    deployments = []
    for qubit in qubits:
        parameters = {
            "menu": menu.model_dump(),
            "calib_dir": calib_dir,
            "successMap": successMap,
            "execution_id": execution_id,
            "qubits": qubit,
        }
        deployments.append(run_deployment("cal-flow/oqtopus-cal-flow", parameters=parameters))

    results = await asyncio.gather(*deployments)

    ## implement gather_results

    for result in results:
        print(result)


def organize_qubits(qubits: list[list[int]], parallel: bool) -> list[list[int]]:
    """Organize qubits into a list of sublists."""
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
    """Flow to calibrate one qubit or a pair of qubits."""
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    parallel = True
    plan = [["45"]]
    if len(menu.one_qubit_calib_plan) == 1:
        parallel = False
    if parallel:
        logger.info("parallel is True")
        # qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        await trigger_cal_flow(menu, calib_dir, successMap, execution_id, plan)
        merge_results_qubits(calib_dir)
        return successMap
    else:
        # qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
        logger.info("parallel is False")
        await trigger_cal_flow(menu, calib_dir, successMap, execution_id, plan)
        merge_results_qubits(calib_dir)
        return successMap


# qubit_calib_plan = [["28", "29"]]
# coupling_calib_plan = [["28-29"]]
