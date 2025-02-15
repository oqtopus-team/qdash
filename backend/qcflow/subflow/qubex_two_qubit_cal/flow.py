import asyncio
from datetime import datetime

from prefect import flow, get_run_logger, task
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qubex.version import get_package_version


@task(name="merge-results")
def merge_results_couplings(calib_dir):
    """Merge results from multiple qubits into calib.json with structure {"couplings": { ... } }.
    If calib.json exists, append new data to the existing couplings."""
    import glob
    import json
    import os

    logger = get_run_logger()
    logger.info(f"Calibration directory: {calib_dir}")

    # Q??-Q??.json ファイルを再帰的に検索
    pattern = os.path.join(calib_dir, "**", "Q??-Q??.json")
    q_files = glob.glob(pattern, recursive=True)
    for file_path in q_files:
        logger.info(f"File: {file_path}")

    calib_json_path = os.path.join(calib_dir, "calib.json")
    # calib.json が存在する場合は読み込み、存在しなければ初期化
    if os.path.exists(calib_json_path):
        with open(calib_json_path, "r", encoding="utf-8") as f:
            merged_data = json.load(f)
        if "couplings" not in merged_data:
            merged_data["couplings"] = {}
    else:
        merged_data = {"couplings": {}}

    # 各ファイルの内容を、ファイル名（拡張子除く）をキーとして追加
    for file_path in q_files:
        qubit_key = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged_data["couplings"][qubit_key] = data
    merged_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 結果を calib.json に上書き保存
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

    print("All Qubits Completed:")
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
    name="qubex-two-qubit-cal-flow",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
    flow_run_name="{execution_id}",
)
async def qubex_two_qubit_cal_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
) -> dict[str, bool]:
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info(f"Qubex version: {get_package_version('qubex')}")
    # parallel = True
    logger.info(f"two_qubit_calib_plan: {menu.two_qubit_calib_plan}")
    qubit_pair = [[28, 29], [28, 30], [29, 31], [30, 31]]
    await trigger_cal_flow(menu, calib_dir, successMap, execution_id, qubit_pair)
    merge_results_couplings(calib_dir)
    # if len(menu.one_qubit_calib_plan) == 1:
    #     parallel = False
    # if parallel:
    #     logger.info("parallel is True")
    #     qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
    #     await trigger_cal_flow(menu, calib_dir, successMap, execution_id, qubits)
    #     return successMap
    # else:
    #     qubits = organize_qubits(menu.one_qubit_calib_plan, parallel)
    #     logger.info("parallel is False")
    #     await trigger_cal_flow(menu, calib_dir, successMap, execution_id, qubits)
    return successMap
