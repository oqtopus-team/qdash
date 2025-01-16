import numpy as np
from prefect import get_run_logger, task
from pydantic import BaseModel
from qubex.experiment import Experiment


class TaskResult(BaseModel):
    name: str
    status: str
    message: str

    def update_status_to_failed(self, message: str):
        """
        update the task result status to failed with the given message.
        """
        self.status = "failed"
        self.message = message

    def update_status_to_success(self, message: str):
        """
        update the task result status to success with the given message.
        """
        self.status = "success"
        self.message = message

    def diagnose(self):
        """
        diagnose the task result and raise an error if the task failed.
        """
        if self.status == "failed":
            raise RuntimeError(f"Task {self.name} failed with message: {self.message}")


class TaskManager(BaseModel):
    check_status: TaskResult = TaskResult(name="check-status", status="pending", message="")
    linkup: TaskResult = TaskResult(name="linkup", status="pending", message="")
    configure: TaskResult = TaskResult(name="configure", status="pending", message="")
    check_noise: TaskResult = TaskResult(name="check-noise", status="pending", message="")
    rabi: TaskResult = TaskResult(name="rabi", status="pending", message="")
    chevron_pattern: TaskResult = TaskResult(name="chevron-pattern", status="pending", message="")
    calibrate_control_frequency: TaskResult = TaskResult(
        name="calibrate-control-frequency", status="pending", message=""
    )
    calibrate_readout_frequency: TaskResult = TaskResult(
        name="calibrate-readout-frequency", status="pending", message=""
    )
    check_rabi: TaskResult = TaskResult(name="check-rabi", status="pending", message="")
    calibrate_hpi_pulse: TaskResult = TaskResult(
        name="calibrate-hpi-pulse", status="pending", message=""
    )
    check_hpi_pulse: TaskResult = TaskResult(name="check-hpi-pulse", status="pending", message="")
    calibrate_pi_pulse: TaskResult = TaskResult(
        name="calibrate-pi-pulse", status="pending", message=""
    )
    check_pi_pulse: TaskResult = TaskResult(name="check-pi-pulse", status="pending", message="")
    t1: TaskResult = TaskResult(name="t1", status="pending", message="")
    t2: TaskResult = TaskResult(name="t2", status="pending", message="")
    effective_control_frequency: TaskResult = TaskResult(
        name="effective-control-frequency", status="pending", message=""
    )


@task(name="check-status")
def check_status_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting check status")
        exp.check_status()
        exp.save_defaults()
    except Exception as e:
        task_manager.check_status.update_status_to_failed(f"Failed to check status: {e}")
        raise RuntimeError(f"Failed to check status: {e}")
    task_manager.check_status.update_status_to_success("Check status is successful.")
    return task_manager.check_status


@task(name="linkup")
def linkup_task(exp: Experiment, task_manager: TaskManager, prev_result: TaskResult) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting linkup")
        exp.linkup()
        exp.save_defaults()
    except Exception as e:
        task_manager.linkup.update_status_to_failed(f"Failed to linkup: {e}")
        raise RuntimeError(f"Failed to linkup: {e}")
    task_manager.linkup.update_status_to_success("Linkup is successful.")
    return task_manager.linkup


@task(name="configure")
def configure_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting configure")
        exp.configure(confirm=False)
        exp.save_defaults()
    except Exception as e:
        task_manager.configure.update_status_to_failed(f"Failed to configure: {e}")
        raise RuntimeError(f"Failed to configure: {e}")
    task_manager.configure.update_status_to_success("Configure is successful.")
    return task_manager.configure


@task(name="check-noise")
def check_noise_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting check noise")
        exp.check_noise()
        exp.save_defaults()
    except Exception as e:
        task_manager.check_noise.update_status_to_failed(f"Failed to check noise: {e}")
        raise RuntimeError(f"Failed to check noise: {e}")
    task_manager.check_noise.update_status_to_success("Check noise is successful.")
    return task_manager.check_noise


@task(name="rabi")
def rabi_task(exp: Experiment, task_manager: TaskManager, prev_result: TaskResult) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    default_rabi_amplitudes = {label: 0.01 for label in exp.qubit_labels}
    try:
        logger.info("Starting Rabi experiment")
        exp.rabi_experiment(
            amplitudes=default_rabi_amplitudes,
            time_range=range(0, 201, 4),
            detuning=0.001,
            shots=300,
            interval=50_000,
        )
        exp.save_defaults()
    except Exception as e:
        task_manager.rabi.update_status_to_failed(f"Failed to run Rabi experiment: {e}")
        raise RuntimeError(f"Failed to run Rabi experiment: {e}")
    task_manager.rabi.update_status_to_success("Rabi experiment is successful.")
    return task_manager.rabi


@task(name="chevron-pattern")
def chevron_pattern_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting Chevron pattern experiment")
        exp.chevron_pattern(
            exp.qubit_labels,
            detuning_range=np.linspace(-0.05, 0.05, 51),
            time_range=np.arange(0, 201, 4),
        )
        exp.save_defaults()
    except Exception as e:
        task_manager.chevron_pattern.update_status_to_failed(
            f"Failed to run Chevron pattern experiment: {e}"
        )
        raise RuntimeError(f"Failed to run Chevron pattern experiment: {e}")
    task_manager.chevron_pattern.update_status_to_success(
        "Chevron pattern experiment is successful."
    )
    return task_manager.chevron_pattern


@task(name="calibrate-control-frequency")
def calibrate_control_frequency_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting control frequency calibration")
        exp.calibrate_control_frequency(
            exp.qubit_labels,
            detuning_range=np.linspace(-0.01, 0.01, 21),
            time_range=range(0, 101, 4),
        )
        exp.save_defaults()
    except Exception as e:
        task_manager.calibrate_control_frequency.update_status_to_failed(
            f"Failed to calibrate control frequency: {e}"
        )
        raise RuntimeError(f"Failed to calibrate control frequency: {e}")
    task_manager.calibrate_control_frequency.update_status_to_success(
        "Control frequency calibration is successful."
    )
    return task_manager.calibrate_control_frequency


@task(name="calibrate-readout-frequency")
def calibrate_readout_frequency_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting readout frequency calibration")
        exp.calibrate_readout_frequency(
            exp.qubit_labels,
            detuning_range=np.linspace(-0.01, 0.01, 21),
            time_range=range(0, 101, 4),
        )
        exp.save_defaults()
    except Exception as e:
        task_manager.calibrate_readout_frequency.update_status_to_failed(
            f"Failed to calibrate readout frequency: {e}"
        )
        raise RuntimeError(f"Failed to calibrate readout frequency: {e}")
    task_manager.calibrate_readout_frequency.update_status_to_success(
        "Readout frequency calibration is successful."
    )
    return task_manager.calibrate_readout_frequency


@task(name="check-rabi")
def check_rabi_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting check rabi")
        exp.check_rabi()
        exp.save_defaults()
    except Exception as e:
        task_manager.check_rabi.update_status_to_failed(f"Failed to check rabi: {e}")
        raise RuntimeError(f"Failed to check rabi: {e}")
    task_manager.check_rabi.update_status_to_success("Check rabi is successful.")
    return task_manager.check_rabi


@task(name="calibrate-hpi-pulse")
def calibrate_hpi_pulse_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting calibrate HPI pulse")
        exp.calibrate_hpi_pulse(
            exp.qubit_labels,
            n_rotations=1,
        )
        exp.save_defaults()
    except Exception as e:
        task_manager.calibrate_hpi_pulse.update_status_to_failed(
            f"Failed to calibrate HPI pulse: {e}"
        )
        raise RuntimeError(f"Failed to calibrate HPI pulse: {e}")
    task_manager.calibrate_hpi_pulse.update_status_to_success("Calibrate HPI pulse is successful.")
    return task_manager.calibrate_hpi_pulse


@task(name="check-hpi-pulse")
def check_hpi_pulse_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting check HPI pulse")
        exp.repeat_sequence(
            exp.hpi_pulse,
            repetitions=20,
        )
        exp.save_defaults()
    except Exception as e:
        task_manager.check_hpi_pulse.update_status_to_failed(f"Failed to check HPI pulse: {e}")
        raise RuntimeError(f"Failed to check HPI pulse: {e}")
    task_manager.check_hpi_pulse.update_status_to_success("Check HPI pulse is successful.")
    return task_manager.check_hpi_pulse


@task(name="calibrate-pi-pulse")
def calibrate_pi_pulse_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting calibrate pi pulse")
        exp.calibrate_pi_pulse(
            exp.qubit_labels,
            n_rotations=1,
        )
        exp.save_defaults()
    except Exception as e:
        task_manager.calibrate_pi_pulse.update_status_to_failed(
            f"Failed to calibrate pi pulse: {e}"
        )
        raise RuntimeError(f"Failed to calibrate pi pulse: {e}")
    task_manager.calibrate_pi_pulse.update_status_to_success("Calibrate pi pulse is successful.")
    return task_manager.calibrate_pi_pulse


@task(name="check-pi-pulse")
def check_pi_pulse_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting check pi pulse")
        exp.repeat_sequence(
            exp.pi_pulse,
            repetitions=20,
        )
        exp.save_defaults()
    except Exception as e:
        task_manager.check_pi_pulse.update_status_to_failed(f"Failed to check pi pulse: {e}")
        raise RuntimeError(f"Failed to check pi pulse: {e}")
    task_manager.check_pi_pulse.update_status_to_success("Check pi pulse is successful.")
    return task_manager.check_pi_pulse


@task(name="t1")
def t1_task(exp: Experiment, task_manager: TaskManager, prev_result: TaskResult) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting T1 experiment")
        t1_result = exp.t1_experiment(
            time_range=np.logspace(
                np.log10(100),
                np.log10(500 * 1000),
                51,
            ),
            save_image=True,
        )
        t1_values = {}
        for qubit in exp.qubit_labels:
            t1_values[qubit] = t1_result.data[qubit].t1 if qubit in t1_result.data else None
        exp.note.put("t1", t1_values)
        exp.note.save()
        print(t1_values)
    except Exception as e:
        task_manager.t1.update_status_to_failed(f"Failed to run T1 experiment: {e}")
        raise RuntimeError(f"Failed to run T1 experiment: {e}")
    task_manager.t1.update_status_to_success("T1 experiment is successful.")
    return task_manager.t1


@task(name="t2")
def t2_task(exp: Experiment, task_manager: TaskManager, prev_result: TaskResult) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting T2 experiment")
        t2_result = exp.t2_experiment(
            exp.qubit_labels,
            time_range=np.logspace(
                np.log10(300),
                np.log10(100 * 1000),
                51,
            ),
            save_image=True,
        )
        t2_values = {}
        for qubit in exp.qubit_labels:
            t2_values[qubit] = t2_result.data[qubit].t2 if qubit in t2_result.data else None
        exp.note.put("t2", t2_values)
        exp.note.save()
        print(t2_values)
    except Exception as e:
        task_manager.t2.update_status_to_failed(f"Failed to run T2 experiment: {e}")
        raise RuntimeError(f"Failed to run T2 experiment: {e}")
    task_manager.t2.update_status_to_success("T2 experiment is successful.")
    return task_manager.t2


@task(name="effective-control-frequency")
def effective_control_frequency_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info("Starting effective control frequency calibration")
        effective_control_frequency_result = exp.obtain_effective_control_frequency(
            exp.qubit_labels,
            time_range=np.arange(0, 20001, 100),
            detuning=0.001,
        )
        effective_freq = effective_control_frequency_result["effective_freq"]
        exp.note.put("effective_freq", effective_freq)
        exp.note.save()
    except Exception as e:
        task_manager.effective_control_frequency.update_status_to_failed(
            f"Failed to calibrate effective control frequency: {e}"
        )
        raise RuntimeError(f"Failed to calibrate effective control frequency: {e}")
    task_manager.effective_control_frequency.update_status_to_success(
        "Effective control frequency calibration is successful."
    )
    return task_manager.effective_control_frequency
