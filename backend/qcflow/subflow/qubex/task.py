import json
from datetime import datetime
from enum import Enum

import numpy as np
from prefect import get_run_logger, task
from pydantic import BaseModel
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class TaskStatus(str, Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskResult(BaseModel):
    name: str
    upstream_task: str
    status: TaskStatus = TaskStatus.SCHEDULED
    message: str
    input_parameters: dict = {}
    output_parameters: dict = {}
    calibrated_at: str = ""
    figure_path: str = ""

    def diagnose(self):
        """
        diagnose the task result and raise an error if the task failed.
        """
        if self.status == TaskStatus.FAILED:
            raise RuntimeError(f"Task {self.name} failed with message: {self.message}")

    def put_input_parameter(self, key: str, value: dict):
        """
        put a parameter to the task result.
        """
        self.input_parameters[key] = value

    def put_output_parameter(self, key: str, value: dict):
        """
        put a parameter to the task result.
        """
        self.output_parameters[key] = value


class TaskManager(BaseModel):
    calib_data_path: str = ""
    qubex_version: str = ""
    execution_id: str = ""
    tasks: dict[str, TaskResult] = {}
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = []
    box_infos: list[dict] = []

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
                status=TaskStatus.SCHEDULED,
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
            self.tasks[task_name].status = TaskStatus.RUNNING
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def update_task_status_to_success(self, task_name: str, message: str = "") -> None:
        """
        Update the task status to success.
        """
        if task_name in self.tasks:
            self.tasks[task_name].status = TaskStatus.SUCCESS
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
            self.tasks[task_name].status = TaskStatus.FAILED
            self.tasks[task_name].message = message
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found.")

    def put_input_parameter(self, task_name: str, key: str, value: dict) -> None:
        """
        Put a parameter to the task result.
        """
        if task_name in self.tasks:
            self.tasks[task_name].input_parameters[key] = value
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found")

    def put_input_parameters(self, task_name: str, input_parameters: dict) -> None:
        """
        Put a parameter to the task result.
        """
        if task_name in self.tasks:
            self.tasks[task_name].input_parameters = input_parameters
            self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()
        else:
            raise ValueError(f"Task '{task_name}' not found")

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

    def put_box_info(self, box_info: dict) -> None:
        """
        Put the box information to the task manager.
        """
        self.box_infos.append(box_info)
        self.save()

    def save(self):
        """
        Save the task manager to a file.
        """
        save_path = f"{self.calib_data_path}/calib_data.json"
        with open(save_path, "w") as f:
            f.write(json.dumps(self.model_dump(), indent=4))


def linespace_to_string(func, *args, **kwargs):
    args_str = ", ".join(map(str, args))
    kwargs_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    combined = ", ".join(filter(None, [args_str, kwargs_str]))
    return f"{func.__name__}({combined})"


def check_status_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.check_status()
    exp.save_defaults()


def linkup_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.linkup()
    exp.save_defaults()


def configure_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    exp.state_manager.load(
        chip_id=exp.chip_id, config_dir=exp.config_path, params_dir=exp.params_path
    )
    exp.state_manager.push(box_ids=exp.box_ids, confirm=False)
    exp.save_defaults()


def dump_box_task(exp: Experiment, task_manager: TaskManager, task_name: str):
    for id in exp.box_ids:
        box_info = {}
        box_info[id] = exp.tool.dump_box(id)
        task_manager.put_box_info(box_info)


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
    detuning_range = np.linspace(-0.01, 0.01, 21)
    time_range = range(0, 101, 4)
    qubit_frequency = exp.calibrate_control_frequency(
        exp.qubit_labels,
        detuning_range=detuning_range,
        time_range=time_range,
    )
    input_params = {
        "detuning_range": linespace_to_string(np.linspace, -0.01, 0.01, 21),
        "time_range": linespace_to_string(range, 0, 101, 4),
        "qubit_frequency": {target: exp.targets[target].frequency for target in exp.qubit_labels},
        "control_amplitude": {
            target: exp.params.control_amplitude[target] for target in exp.qubit_labels
        },
        "shots": DEFAULT_SHOTS,
        "interval": DEFAULT_INTERVAL,
    }

    exp.save_defaults()
    task_manager.put_input_parameters(task_name, input_params)
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
    "DumpBox": dump_box_task,
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
