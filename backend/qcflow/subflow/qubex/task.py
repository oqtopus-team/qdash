from prefect import get_run_logger, task
from pydantic import BaseModel
from qubex.experiment import Experiment

logger = get_run_logger()


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
        logger.info(f"Task {self.name} failed with message: {message}")

    def update_status_to_success(self, message: str):
        """
        update the task result status to success with the given message.
        """
        self.status = "success"
        self.message = message
        logger.info(f"Task {self.name} is successful with message: {message}")

    def diagnose(self):
        """
        diagnose the task result and raise an error if the task failed.
        """
        if self.status == "failed":
            logger.error(f"Task {self.name} failed with message: {self.message}")
            raise RuntimeError(f"Task {self.name} failed with message: {self.message}")
        logger.info(f"Task {self.name} is successful with message: {self.message}")


class TaskManager(BaseModel):
    check_status: TaskResult = TaskResult(name="check-status", status="pending", message="")
    linkup: TaskResult = TaskResult(name="linkup", status="pending", message="")
    configure: TaskResult = TaskResult(name="configure", status="pending", message="")
    check_noise: TaskResult = TaskResult(name="check-noise", status="pending", message="")
    rabi: TaskResult = TaskResult(name="rabi", status="pending", message="")


@task(name="check-status")
def check_status_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    prev_result.diagnose()
    try:
        logger.info("Starting check status")
        exp.check_status()
    except Exception as e:
        task_manager.check_status.update_status_to_failed(f"Failed to check status: {e}")
        raise RuntimeError(f"Failed to check status: {e}")
    task_manager.check_status.update_status_to_success("Check status is successful.")
    return task_manager.check_status


@task(name="linkup")
def linkup_task(exp: Experiment, task_manager: TaskManager, prev_result: TaskResult) -> TaskResult:
    prev_result.diagnose()
    try:
        logger.info("Starting linkup")
        exp.linkup()
    except Exception as e:
        task_manager.linkup.update_status_to_failed(f"Failed to linkup: {e}")
        raise RuntimeError(f"Failed to linkup: {e}")
    task_manager.linkup.update_status_to_success("Linkup is successful.")
    return task_manager.linkup


@task(name="configure")
def configure_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    prev_result.diagnose()
    try:
        logger.info("Starting configure")
        exp.configure(confirm=False)
    except Exception as e:
        task_manager.configure.update_status_to_failed(f"Failed to configure: {e}")
        raise RuntimeError(f"Failed to configure: {e}")
    task_manager.configure.update_status_to_success("Configure is successful.")
    return task_manager.configure


@task(name="check-noise")
def check_noise_task(
    exp: Experiment, task_manager: TaskManager, prev_result: TaskResult
) -> TaskResult:
    prev_result.diagnose()
    try:
        logger.info("Starting check noise")
        exp.check_noise()
    except Exception as e:
        task_manager.check_noise.update_status_to_failed(f"Failed to check noise: {e}")
        raise RuntimeError(f"Failed to check noise: {e}")
    task_manager.check_noise.update_status_to_success("Check noise is successful.")
    return task_manager.check_noise


@task(name="rabi")
def rabi_task(exp: Experiment, task_manager: TaskManager, prev_result: TaskResult) -> TaskResult:
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
    except Exception as e:
        task_manager.rabi.update_status_to_failed(f"Failed to run Rabi experiment: {e}")
        raise RuntimeError(f"Failed to run Rabi experiment: {e}")
    task_manager.rabi.update_status_to_success("Rabi experiment is successful.")
    return task_manager.rabi
