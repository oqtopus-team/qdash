import numpy as np
from prefect import get_run_logger, task
from qcflow.subflow.qubex.protocols.box_setup.check_noise import CheckNoise
from qcflow.subflow.qubex.protocols.box_setup.configure import Configure
from qcflow.subflow.qubex.protocols.box_setup.dump_box import DumpBox
from qcflow.subflow.qubex.protocols.box_setup.link_up import LinkUp
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_effective_qubit_frequency import (
    CheckEffectiveQubitFrequency,
)
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_hpi_pulse import CheckHPIPulse
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_pi_pulse import CheckPIPulse
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_qubit_frequency import (
    CheckQubitFrequency,
)
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_rabi import CheckRabi
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_readout_frequency import (
    CheckReadoutFrequency,
)
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_status import CheckStatus
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_t1 import CheckT1
from qcflow.subflow.qubex.protocols.one_qubit_coarse.check_t2 import CheckT2
from qcflow.subflow.qubex.protocols.one_qubit_coarse.chevron_pattern import ChevronPattern
from qcflow.subflow.qubex.protocols.one_qubit_coarse.create_hpi_pulse import CreateHPIPulse
from qcflow.subflow.qubex.protocols.one_qubit_coarse.create_pi_pulse import CreatePIPulse
from qcflow.subflow.qubex.protocols.one_qubit_coarse.rabi_oscillation import RabiOscillation
from qubex.experiment import Experiment
from qubex.experiment.experiment import RABI_TIME_RANGE
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS
from subflow.qubex.manager import TaskManager, TaskResult

task_classes = {
    "CheckStatus": CheckStatus(),
    "LinkUp": LinkUp(),
    "Configure": Configure(),
    "DumpBox": DumpBox(),
    "CheckNoise": CheckNoise(),
    "RabiOscillation": RabiOscillation(),
    "ChevronPattern": ChevronPattern(),
    "CheckQubitFrequency": CheckQubitFrequency(
        detuning_range=np.linspace(-0.01, 0.01, 21),
        time_range=range(0, 101, 4),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckReadoutFrequency": CheckReadoutFrequency(
        detuning_range=np.linspace(-0.01, 0.01, 21),
        time_range=range(0, 101, 4),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckRabi": CheckRabi(
        time_range=RABI_TIME_RANGE,
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CreateHPIPulse": CreateHPIPulse(),
    "CheckHPIPulse": CheckHPIPulse(),
    "CreatePIPulse": CreatePIPulse(),
    "CheckPIPulse": CheckPIPulse(),
    "CheckT1": CheckT1(),
    "CheckT2": CheckT2(),
    "CheckEffectiveQubitFrequency": CheckEffectiveQubitFrequency(),
}


def validate_task_name(task_name: str):
    if task_name not in task_classes:
        raise ValueError(f"Invalid task name: {task_name}")


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
        task_manager.start_each_task(task_name)
        task_manager.update_task_status_to_running(task_name)
        task_class = task_classes[task_name]
        task_class.execute(exp, task_manager, task_name)
        logger.info(f"Task {task_name} is successful.")
        task_manager.update_task_status_to_success(task_name, f"{task_name} is successful.")
    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}")
        task_manager.update_task_status_to_failed(task_name, f"Failed to execute {task_name}: {e}")
        raise RuntimeError(f"Task {task_name} failed: {e}")
    finally:
        logger.info(f"Ending task: {task_name}")
        task_manager.end_each_task(task_name)
    return task_manager.get_task(task_name)
