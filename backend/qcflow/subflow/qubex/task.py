import json
from datetime import datetime

import numpy as np
from prefect import get_run_logger, task
from pydantic import BaseModel
from qubex.experiment import Experiment


class TaskResult(BaseModel):
    name: str
    upstream_task: str
    status: str
    message: str
    input_parameters: dict = {}
    output_parameters: dict = {}
    calibrated_at: str = ""
    figure_path: str = ""

    def diagnose(self):
        """
        diagnose the task result and raise an error if the task failed.
        """
        if self.status == "failed":
            raise RuntimeError(f"Task {self.name} failed with message: {self.message}")

    def put_output_parameter(self, key: str, value: dict):
        """
        put a parameter to the task result.
        """
        self.output_parameters[key] = value


class TaskManager(BaseModel):
    calib_data_path: str = ""
    execution_id: str = ""
    tasks: dict[str, TaskResult] = {}
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = []

    def __init__(
        self,
        execution_id: str,
        calib_data_path: str,
        task_names: list[str],
        tags: list[str],
        **kargs,
    ):
        super().__init__(**kargs)
        if not task_names or not isinstance(task_names, list):
            raise ValueError("task_names must be a non-empty list of strings.")
        self.calib_data_path = calib_data_path
        self.execution_id = execution_id
        self.tasks = {
            name: TaskResult(
                name=name,
                upstream_task=task_names[i - 1] if i > 0 else "",
                status="scheduled",
                message="",
                input_parameters={},
                output_parameters={},
                calibrated_at="",
            )
            for i, name in enumerate(task_names)
        }
        self.tags = tags
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def update_task_status_to_running(self, task_name: str) -> None:
        """
        Update the task status to running.
        """
        if task_name in self.tasks:
            self.tasks[task_name].status = "running"
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def update_task_status_to_success(self, task_name: str, message: str = "") -> None:
        """
        Update the task status to success.
        """
        if task_name in self.tasks:
            self.tasks[task_name].status = "success"
            self.tasks[task_name].message = message
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.tasks[task_name].calibrated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def update_task_status_to_failed(self, task_name: str, message: str = "") -> None:
        """
        Update the task status to failed.
        """
        if task_name in self.tasks:
            self.tasks[task_name].status = "failed"
            self.tasks[task_name].message = message
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def put_output_parameter(self, task_name: str, key: str, value: dict) -> None:
        """
        Put a parameter to the task result.
        """
        if task_name in self.tasks:
            self.tasks[task_name].output_parameters[key] = value
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def get_task(self, task_name: str) -> TaskResult:
        """
        Get the task result by task name.
        """
        if task_name in self.tasks:
            return self.tasks[task_name]
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def save(self):
        """
        Save the task manager to a file.
        """
        save_path = f"{self.calib_data_path}/calib_data.json"
        with open(save_path, "w") as f:
            f.write(json.dumps(self.model_dump(), indent=4))


def check_status_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.check_status()
    exp.save_defaults()


def linkup_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.linkup()
    exp.save_defaults()


def configure_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.configure(confirm=False)
    exp.save_defaults()


def check_noise_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.check_noise()
    exp.save_defaults()


def rabi_task(exp: Experiment, task_manager: TaskManager, tasks_name: str):
    default_rabi_amplitudes = {label: 0.01 for label in exp.qubit_labels}
    exp.rabi_experiment(
        amplitudes=default_rabi_amplitudes,
        time_range=range(0, 201, 4),
        detuning=0.001,
        shots=300,
        interval=50_000,
    )
    exp.save_defaults()


def chevron_pattern_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.chevron_pattern(
        exp.qubit_labels,
        detuning_range=np.linspace(-0.05, 0.05, 51),
        time_range=np.arange(0, 201, 4),
    )
    exp.save_defaults()


def calibrate_control_frequency_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    qubit_frequency = exp.calibrate_control_frequency(
        exp.qubit_labels,
        detuning_range=np.linspace(-0.01, 0.01, 21),
        time_range=range(0, 101, 4),
    )
    exp.save_defaults()
    task_manager.put_output_parameter(task_name, "qubit_frequency", qubit_frequency)


def calibrate_readout_frequency_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    readout_frequency = exp.calibrate_readout_frequency(
        exp.qubit_labels,
        detuning_range=np.linspace(-0.01, 0.01, 21),
        time_range=range(0, 101, 4),
    )
    exp.save_defaults()
    task_manager.put_output_parameter(task_name, "readout_frequency", readout_frequency)


def check_rabi_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    rabi_result = exp.check_rabi()
    exp.save_defaults()
    rabi_params = {key: value.rabi_param.__dict__ for key, value in rabi_result.data.items()}
    task_manager.put_output_parameter(task_name, "rabi_params", rabi_params)


def calibrate_hpi_pulse_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    hpi_result = exp.calibrate_hpi_pulse(
        exp.qubit_labels,
        n_rotations=1,
    )
    exp.save_defaults()
    hpi_amplitudes = {}
    for qubit in exp.qubit_labels:
        hpi_amplitudes[qubit] = (
            hpi_result.data[qubit].calib_value if qubit in hpi_result.data else None
        )
    task_manager.put_output_parameter(task_name, "hpi_amplitude", hpi_amplitudes)


def check_hpi_pulse_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.repeat_sequence(
        exp.hpi_pulse,
        repetitions=20,
    )
    exp.save_defaults()


def calibrate_pi_pulse_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    pi_result = exp.calibrate_pi_pulse(
        exp.qubit_labels,
        n_rotations=1,
    )
    exp.save_defaults()
    pi_amplitudes = {}
    for qubit in exp.qubit_labels:
        pi_amplitudes[qubit] = (
            pi_result.data[qubit].calib_value if qubit in pi_result.data else None
        )
    task_manager.put_output_parameter(task_name, "pi_amplitude", pi_amplitudes)


def check_pi_pulse_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.repeat_sequence(
        exp.pi_pulse,
        repetitions=20,
    )
    exp.save_defaults()


def t1_task(exp: Experiment, task_manager: TaskManager, task_name: str):
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
    task_manager.put_output_parameter(task_name, "t1", t1_values)


def t2_task(exp: Experiment, task_manager: TaskManager, task_name: str):
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
    task_manager.put_output_parameter(task_name, "t2", t2_values)


def effective_control_frequency_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    effective_control_frequency_result = exp.obtain_effective_control_frequency(
        exp.qubit_labels,
        time_range=np.arange(0, 20001, 100),
        detuning=0.001,
    )
    task_manager.put_output_parameter(
        task_name, "effective_qubit_frequency", effective_control_frequency_result["effective_freq"]
    )


task_functions = {
    "CheckStatus": check_status_task,
    "LinkUp": linkup_task,
    "Configure": configure_task,
    "CheckNoise": check_noise_task,
    "RabiOscillation": rabi_task,
    "ChevronPattern": chevron_pattern_task,
    "CheckQubitFrequency": calibrate_control_frequency_task,
    "CheckReadoutFrequency": calibrate_readout_frequency_task,
    "CheckRabi": check_rabi_task,
    "CreateHPIPulse": calibrate_hpi_pulse_task,
    "CheckHPIPulse": check_hpi_pulse_task,
    "CreatePIPulse": calibrate_pi_pulse_task,
    "CheckPIPulse": check_pi_pulse_task,
    "CheckT1": t1_task,
    "CheckT2": t2_task,
    "CheckEffectiveQubitFrequency": effective_control_frequency_task,
}


@task(name="execute-dynamic-task", task_run_name="{task_name}")
def execute_dynamic_task(
    exp: Experiment,
    task_manager: TaskManager,
    task_name: str,
    prev_result: TaskResult,
) -> TaskResult:
    logger = get_run_logger()
    prev_result.diagnose()
    try:
        logger.info(f"Starting task: {task_name}")
        task_manager.update_task_status_to_running(task_name)
        task_function = task_functions[task_name]
        task_function(exp, task_manager, task_name)
        task_manager.update_task_status_to_success(task_name, f"{task_name} is successful.")
    except Exception as e:
        task_manager.update_task_status_to_failed(task_name, f"Failed to execute {task_name}: {e}")
        raise RuntimeError(f"Task {task_name} failed: {e}")

    return task_manager.get_task(task_name)
