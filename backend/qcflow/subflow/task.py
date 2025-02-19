import numpy as np
from prefect import get_run_logger, task
from qcflow.subflow.protocols.benchmark.randomized_benchmarking import RandomizedBenchmarking
from qcflow.subflow.protocols.benchmark.x90_interleaved_randomized_benchmarking import (
    X90InterleavedRandomizedBenchmarking,
)
from qcflow.subflow.protocols.benchmark.x180_interleaved_randoized_benchmarking import (
    X180InterleavedRandomizedBenchmarking,
)
from qcflow.subflow.protocols.benchmark.zx90_interleaved_randoized_benchmarking import (
    ZX90InterleavedRandomizedBenchmarking,
)
from qcflow.subflow.protocols.box_setup.check_noise import CheckNoise

# from qcflow.subflow.protocols.box_setup.configure import Configure
from qcflow.subflow.protocols.box_setup.dump_box import DumpBox
from qcflow.subflow.protocols.box_setup.link_up import LinkUp
from qcflow.subflow.protocols.measurement.readout_classification import ReadoutClassification
from qcflow.subflow.protocols.one_qubit_coarse.check_effective_qubit_frequency import (
    CheckEffectiveQubitFrequency,
)
from qcflow.subflow.protocols.one_qubit_coarse.check_hpi_pulse import CheckHPIPulse
from qcflow.subflow.protocols.one_qubit_coarse.check_pi_pulse import CheckPIPulse
from qcflow.subflow.protocols.one_qubit_coarse.check_qubit_frequency import (
    CheckQubitFrequency,
)
from qcflow.subflow.protocols.one_qubit_coarse.check_rabi import CheckRabi
from qcflow.subflow.protocols.one_qubit_coarse.check_readout_frequency import (
    CheckReadoutFrequency,
)
from qcflow.subflow.protocols.one_qubit_coarse.check_status import CheckStatus
from qcflow.subflow.protocols.one_qubit_coarse.check_t1 import CheckT1
from qcflow.subflow.protocols.one_qubit_coarse.check_t2_echo import CheckT2Echo
from qcflow.subflow.protocols.one_qubit_coarse.chevron_pattern import ChevronPattern
from qcflow.subflow.protocols.one_qubit_coarse.create_hpi_pulse import CreateHPIPulse
from qcflow.subflow.protocols.one_qubit_coarse.create_pi_pulse import CreatePIPulse
from qcflow.subflow.protocols.one_qubit_coarse.rabi_oscillation import RabiOscillation
from qcflow.subflow.protocols.one_qubit_fine.check_drag_hpi_pulse import CheckDRAGHPIPulse
from qcflow.subflow.protocols.one_qubit_fine.check_drag_pi_pulse import CheckDRAGPIPulse
from qcflow.subflow.protocols.one_qubit_fine.create_drag_hpi_pulse import CreateDRAGHPIPulse
from qcflow.subflow.protocols.one_qubit_fine.create_drag_pi_pulse import CreateDRAGPIPulse
from qcflow.subflow.protocols.two_qubit.check_cross_resonance import CheckCrossResonance
from qcflow.subflow.protocols.two_qubit.create_fine_zx90 import CreateFineZX90
from qcflow.subflow.protocols.two_qubit.create_zx90 import CreateZX90
from qcflow.subflow.protocols.two_qubit.optimize_zx90 import OptimizeZX90
from qcflow.subflow.task_manager import CouplingTask, GlobalTask, QubitTask, TaskManager, TaskResult
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import (
    CALIBRATION_SHOTS,
    HPI_DURATION,
    PI_DURATION,
    RABI_TIME_RANGE,
)
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS

task_classes = {
    "CheckStatus": {
        "instance": CheckStatus(),
        "task_type": CheckStatus.task_type,
    },
    "LinkUp": {
        "instance": LinkUp(),
        "task_type": LinkUp.task_type,
    },
    # "Configure": {
    #     "instance": Configure(),
    #     "task_type": Configure.task_type,
    # },
    "DumpBox": {
        "instance": DumpBox(),
        "task_type": DumpBox.task_type,
    },
    "CheckNoise": {
        "instance": CheckNoise(),
        "task_type": CheckNoise.task_type,
    },
    "RabiOscillation": {
        "instance": RabiOscillation(),
        "task_type": RabiOscillation.task_type,
    },
    "ChevronPattern": {
        "instance": ChevronPattern(),
        "task_type": ChevronPattern.task_type,
    },
    "CheckQubitFrequency": {
        "instance": CheckQubitFrequency(
            detuning_range=np.linspace(-0.01, 0.01, 21),
            time_range=range(0, 101, 4),
            shots=DEFAULT_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CheckQubitFrequency.task_type,
    },
    "CheckReadoutFrequency": {
        "instance": CheckReadoutFrequency(
            detuning_range=np.linspace(-0.01, 0.01, 21),
            time_range=range(0, 101, 4),
            shots=DEFAULT_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CheckReadoutFrequency.task_type,
    },
    "CheckRabi": {
        "instance": CheckRabi(
            time_range=RABI_TIME_RANGE,
            shots=DEFAULT_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CheckRabi.task_type,
    },
    "CreateHPIPulse": {
        "instance": CreateHPIPulse(
            hpi_length=HPI_DURATION,
            shots=CALIBRATION_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CreateHPIPulse.task_type,
    },
    "CheckHPIPulse": {
        "instance": CheckHPIPulse(),
        "task_type": CheckHPIPulse.task_type,
    },
    "CreatePIPulse": {
        "instance": CreatePIPulse(
            pi_length=PI_DURATION,
            shots=CALIBRATION_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CreatePIPulse.task_type,
    },
    "CheckPIPulse": {
        "instance": CheckPIPulse(),
        "task_type": CheckPIPulse.task_type,
    },
    "CheckT1": {
        "instance": CheckT1(
            time_range=np.logspace(
                np.log10(100),
                np.log10(500 * 1000),
                51,
            ),
            shots=DEFAULT_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CheckT1.task_type,
    },
    "CheckT2Echo": {
        "instance": CheckT2Echo(
            time_range=np.logspace(
                np.log10(300),
                np.log10(100 * 1000),
                51,
            ),
            shots=DEFAULT_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CheckT2Echo.task_type,
    },
    "CheckEffectiveQubitFrequency": {
        "instance": CheckEffectiveQubitFrequency(
            detuning=0.001,
            time_range=np.arange(0, 20001, 100),
            shots=DEFAULT_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CheckEffectiveQubitFrequency.task_type,
    },
    "CreateDRAGHPIPulse": {
        "instance": CreateDRAGHPIPulse(
            hpi_length=HPI_DURATION,
            shots=CALIBRATION_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CreateDRAGHPIPulse.task_type,
    },
    "CheckDRAGHPIPulse": {
        "instance": CheckDRAGHPIPulse(),
        "task_type": CheckDRAGHPIPulse.task_type,
    },
    "CreateDRAGPIPulse": {
        "instance": CreateDRAGPIPulse(
            pi_length=PI_DURATION,
            shots=CALIBRATION_SHOTS,
            interval=DEFAULT_INTERVAL,
        ),
        "task_type": CreateDRAGPIPulse.task_type,
    },
    "CheckDRAGPIPulse": {
        "instance": CheckDRAGPIPulse(),
        "task_type": CheckDRAGPIPulse.task_type,
    },
    "ReadoutClassification": {
        "instance": ReadoutClassification(),
        "task_type": ReadoutClassification.task_type,
    },
    "RandomizedBenchmarking": {
        "instance": RandomizedBenchmarking(),
        "task_type": RandomizedBenchmarking.task_type,
    },
    "X90InterleavedRandomizedBenchmarking": {
        "instance": X90InterleavedRandomizedBenchmarking(),
        "task_type": X90InterleavedRandomizedBenchmarking.task_type,
    },
    "X180InterleavedRandomizedBenchmarking": {
        "instance": X180InterleavedRandomizedBenchmarking(),
        "task_type": X180InterleavedRandomizedBenchmarking.task_type,
    },
    "ZX90InterleavedRandomizedBenchmarking": {
        "instance": ZX90InterleavedRandomizedBenchmarking(),
        "task_type": ZX90InterleavedRandomizedBenchmarking.task_type,
    },
    "CheckCrossResonance": {
        "instance": CheckCrossResonance(),
        "task_type": CheckCrossResonance.task_type,
    },
    "CreateFineZX90": {
        "instance": CreateFineZX90(),
        "task_type": CreateFineZX90.task_type,
    },
    "CreateZX90": {
        "instance": CreateZX90(),
        "task_type": CreateZX90.task_type,
    },
    "OptimizeZX90": {
        "instance": OptimizeZX90(),
        "task_type": OptimizeZX90.task_type,
    },
}


def validate_task_name(task_names: list[str]) -> list[str]:
    """Validate task names."""
    for task_name in task_names:
        if task_name not in task_classes:
            raise ValueError(f"Invalid task name: {task_name}")
    return task_names


def build_workflow(task_names: list[str], qubits: list[str]) -> TaskResult:
    """Build workflow."""
    task_result = TaskResult()
    global_previous_task_id = ""
    qubit_previous_task_id = {qubit: "" for qubit in qubits}
    coupling_previous_task_id = {qubit: "" for qubit in qubits}
    for name in task_names:
        if name in task_classes:
            task_class = task_classes[name]
            task_type = task_class["task_type"]

            if task_type == "global":
                task = GlobalTask(name=name, upstream_id=global_previous_task_id)
                task_result.global_tasks.append(task)
                global_previous_task_id = task.id

            elif task_type == "qubit":
                for qubit in qubits:
                    task = QubitTask(
                        name=name, upstream_id=qubit_previous_task_id[qubit], qid=qubit
                    )
                    task_result.qubit_tasks.setdefault(qubit, []).append(task)
                    qubit_previous_task_id[qubit] = task.id

            elif task_type == "coupling":
                for qubit in qubits:
                    task = CouplingTask(
                        name=name, upstream_id=coupling_previous_task_id[qubit], qid=qubit
                    )
                    task_result.coupling_tasks.setdefault(qubit, []).append(task)
                    coupling_previous_task_id[qubit] = task.id
            else:
                raise ValueError(f"Task type {task_type} not found.")
        else:
            raise ValueError(f"Task {name} not found.")

    return task_result


@task(name="execute-dynamic-task", task_run_name="{task_name}")
def execute_dynamic_task(
    exp: Experiment,
    task_manager: TaskManager,
    task_name: str,
) -> TaskManager:
    """Execute dynamic task."""
    logger = get_run_logger()
    task_manager.diagnose()
    try:
        logger.info(f"Starting task: {task_name}")
        qids = [convert_qid(qid) for qid in exp.qubit_labels]
        task_map = task_classes[task_name]
        task_type = task_map["task_type"]
        task_instance = task_map["instance"]
        task_manager.start_all_qid_tasks(task_name, task_type, qids)
        logger.info(f"Running task: {task_name}, id: {task_manager.id}")
        task_manager.update_all_qid_task_status_to_running(
            task_name=task_name, message=f"running {task_name} ...", task_type=task_type, qids=qids
        )
        task_instance.execute(exp, task_manager)
        logger.info(f"Task {task_name} is successful, id: {task_manager.id}")
        task_manager.update_all_qid_task_status_to_completed(
            task_name=task_name, message=f"{task_name} is completed", task_type=task_type, qids=qids
        )
    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_manager.id}")
        task_manager.update_all_qid_task_status_to_failed(
            task_name=task_name, message=f"{task_name} failed", task_type=task_type, qids=qids
        )
        raise RuntimeError(f"Task {task_name} failed: {e}")
    finally:
        logger.info(f"Ending task: {task_name}, id: {task_manager.id}")
        task_manager.end_all_qid_tasks(task_name, task_type, qids)
        task_manager.save()
    return task_manager
