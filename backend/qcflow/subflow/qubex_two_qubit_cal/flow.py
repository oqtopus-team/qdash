import asyncio

from prefect import flow, get_run_logger
from prefect.deployments import run_deployment
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qubex.version import get_package_version


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
    qubit_pair = [[7, 5]]
    await trigger_cal_flow(menu, calib_dir, successMap, execution_id, qubit_pair)
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
