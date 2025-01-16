from prefect import flow, get_run_logger
from prefect.task_runners import SequentialTaskRunner
from qcflow.schema.menu import Menu
from qcflow.subflow.qubex.task import (
    TaskManager,
    TaskResult,
    calibrate_control_frequency_task,
    calibrate_hpi_pulse_task,
    calibrate_pi_pulse_task,
    # rabi_task,
    calibrate_readout_frequency_task,
    check_hpi_pulse_task,
    check_noise_task,
    check_pi_pulse_task,
    check_rabi_task,
    check_status_task,
    # chevron_pattern_task,
    configure_task,
    effective_control_frequency_task,
    linkup_task,
    t1_task,
    t2_task,
)
from qubex.experiment import Experiment


@flow(
    name="qubex-flow",
    task_runner=SequentialTaskRunner(),
    log_prints=True,
    flow_run_name="{execution_id}",
)
def qubex_flow(
    menu: Menu,
    calib_dir: str,
    successMap: dict[str, bool],
    execution_id: str,
) -> dict[str, bool]:
    logger = get_run_logger()
    logger.info(f"Menu name: {menu.name}")
    logger.info("Starting qubex_flow")
    exp = Experiment(
        chip_id="64Q",
        qubits=[5, 7],
        config_dir="/home/shared/config",
    )
    exp.note.clear()
    task_manager = TaskManager()
    dummy_result = TaskResult(name="dummy", status="pending", message="")
    check_status_result = check_status_task.submit(exp, task_manager, dummy_result).result()
    linkup_result = linkup_task.submit(exp, task_manager, check_status_result).result()
    configure_result = configure_task.submit(exp, task_manager, linkup_result).result()
    check_noise_result = check_noise_task.submit(exp, task_manager, configure_result).result()
    # rabi_result = rabi_task.submit(exp, task_manager, check_noise_result).result()
    # chevron_pattern_result = chevron_pattern_task.submit(exp, task_manager, rabi_result).result()
    calibrate_control_frequency_result = calibrate_control_frequency_task.submit(
        exp, task_manager, check_noise_result
    ).result()
    calibrate_readout_frequency_result = calibrate_readout_frequency_task.submit(
        exp, task_manager, calibrate_control_frequency_result
    ).result()
    check_rabi_result = check_rabi_task.submit(
        exp, task_manager, calibrate_readout_frequency_result
    ).result()
    calibrate_hpi_pulse_result = calibrate_hpi_pulse_task.submit(
        exp, task_manager, check_rabi_result
    ).result()
    check_hpi_pulse_result = check_hpi_pulse_task.submit(
        exp, task_manager, calibrate_hpi_pulse_result
    ).result()
    calibrate_pi_pulse_result = calibrate_pi_pulse_task.submit(
        exp, task_manager, check_hpi_pulse_result
    ).result()
    check_pi_pulse_result = check_pi_pulse_task.submit(
        exp, task_manager, calibrate_pi_pulse_result
    ).result()
    t1_result = t1_task.submit(exp, task_manager, check_pi_pulse_result).result()
    t2_result = t2_task.submit(exp, task_manager, t1_result).result()
    effective_control_frequency_result = effective_control_frequency_task.submit(
        exp, task_manager, t2_result
    ).result()

    logger.info(f"Final State: {task_manager.model_dump()}")
    return successMap
