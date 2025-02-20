import numpy as np
from neodbmodel.execution_history import ExecutionHistoryDocument
from neodbmodel.qubit import QubitDocument
from neodbmodel.task_history import TaskHistoryDocument
from prefect import flow, get_run_logger, task
from qcflow.subflow.execution_manager import ExecutionManager
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
from qcflow.subflow.protocols.box_setup.configure import Configure
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
from repository.initialize import initialize

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
    "CreateHPIPulse": CreateHPIPulse(
        hpi_length=HPI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckHPIPulse": CheckHPIPulse(),
    "CreatePIPulse": CreatePIPulse(
        pi_length=PI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckPIPulse": CheckPIPulse(),
    "CheckT1": CheckT1(
        time_range=np.logspace(
            np.log10(100),
            np.log10(500 * 1000),
            51,
        ),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckT2Echo": CheckT2Echo(
        time_range=np.logspace(
            np.log10(300),
            np.log10(100 * 1000),
            51,
        ),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckEffectiveQubitFrequency": CheckEffectiveQubitFrequency(
        detuning=0.001,
        time_range=np.arange(0, 20001, 100),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CreateDRAGHPIPulse": CreateDRAGHPIPulse(
        hpi_length=HPI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckDRAGHPIPulse": CheckDRAGHPIPulse(),
    "CreateDRAGPIPulse": CreateDRAGPIPulse(
        pi_length=PI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckDRAGPIPulse": CheckDRAGPIPulse(),
    "ReadoutClassification": ReadoutClassification(),
    "RandomizedBenchmarking": RandomizedBenchmarking(),
    "X90InterleavedRandomizedBenchmarking": X90InterleavedRandomizedBenchmarking(),
    "X180InterleavedRandomizedBenchmarking": X180InterleavedRandomizedBenchmarking(),
    "ZX90InterleavedRandomizedBenchmarking": ZX90InterleavedRandomizedBenchmarking(),
    "CheckCrossResonance": CheckCrossResonance(),
    "CreateFineZX90": CreateFineZX90(),
    "CreateZX90": CreateZX90(),
    "OptimizeZX90": OptimizeZX90(),
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
            this_task = task_classes[name]

            if this_task.is_global_task():
                task = GlobalTask(name=name, upstream_id=global_previous_task_id)
                task_result.global_tasks.append(task)
                global_previous_task_id = task.task_id

            elif this_task.is_qubit_task():
                for qubit in qubits:
                    task = QubitTask(
                        name=name, upstream_id=qubit_previous_task_id[qubit], qid=qubit
                    )
                    task_result.qubit_tasks.setdefault(qubit, []).append(task)
                    qubit_previous_task_id[qubit] = task.task_id
            elif this_task.is_coupling_task():
                for qubit in qubits:
                    task = CouplingTask(
                        name=name, upstream_id=coupling_previous_task_id[qubit], qid=qubit
                    )
                    task_result.coupling_tasks.setdefault(qubit, []).append(task)
                    coupling_previous_task_id[qubit] = task.task_id
            else:
                raise ValueError(f"Task type {this_task.get_task_type()} not found.")
        else:
            raise ValueError(f"Task {name} not found.")

    return task_result


initialize()


@flow(flow_run_name="{qid}")
def cal_sequence(
    exp: Experiment,
    task_manager: TaskManager,
    task_names: list[str],
    qid: str,
) -> TaskManager:
    """Calibrate in sequence."""
    logger = get_run_logger()
    try:
        for task_name in task_names:
            if task_name in task_classes:
                task_type = task_classes[task_name].get_task_type()
                if task_manager.this_task_is_completed(
                    task_name=task_name, task_type=task_type, qid=qid
                ):
                    logger.info(f"Task {task_name} is already completed")
                    continue
                logger.info(f"Starting task: {task_name}")
                task_manager = execute_dynamic_task_by_qid(
                    exp=exp, task_manager=task_manager, task_name=task_name, qid=qid
                )
    except Exception as e:
        logger.error(f"Failed to execute task: {e}")
    finally:
        logger.info("Ending all processes")
    return task_manager


@task(name="execute-dynamic-task", task_run_name="{task_name}")
def execute_dynamic_task_by_qid(
    exp: Experiment,
    task_manager: TaskManager,
    task_name: str,
    qid: str,
) -> TaskManager:
    """Execute dynamic task."""
    logger = get_run_logger()
    task_manager.diagnose()
    try:
        this_task = task_classes[task_name]
        task_type = this_task.get_task_type()
        execution_manager = ExecutionManager.load_from_file(task_manager.calib_dir)
        logger.info(f"Starting task: {task_name}")
        task_manager.start_task(task_name, task_type, qid)
        logger.info(f"Running task: {task_name}, id: {task_manager.id}")
        task_manager.update_task_status_to_running(
            task_name=task_name, message=f"running {task_name} ...", task_type=task_type, qid=qid
        )
        execution_manager = execution_manager.reload().update_with_task_manager(
            task_manager=task_manager
        )
        this_task.execute(exp, task_manager, target=qid)
        execution_manager = execution_manager.reload().update_with_task_manager(
            task_manager=task_manager
        )
        ExecutionHistoryDocument.update_document(execution_manager)
        task_manager.update_task_status_to_completed(
            task_name=task_name, message=f"{task_name} is completed", task_type=task_type, qid=qid
        )
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskHistoryDocument.upsert_document(task=executed_task, execution_manager=execution_manager)
        output_parameters = task_manager.get_output_parameter_by_task_name(
            task_name=task_name, task_type=task_type, qid=qid
        )
        if output_parameters:
            QubitDocument.update_calib_data(
                qid=qid, chip_id=execution_manager.chip_id, output_parameters=output_parameters
            )
    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_manager.id}")
        task_manager.update_task_status_to_failed(
            task_name=task_name, message=f"{task_name} failed", task_type=task_type, qid=qid
        )
        execution_manager = execution_manager.reload().update_with_task_manager(
            task_manager=task_manager
        )
        raise RuntimeError(f"Task {task_name} failed: {e}")
    finally:
        logger.info(f"Ending task: {task_name}, id: {task_manager.id}")
        task_manager.end_task(task_name, task_type, qid)
        task_manager.save()
        execution_manager = execution_manager.reload().update_with_task_manager(
            task_manager=task_manager
        )
        ExecutionHistoryDocument.update_document(execution_manager)
    return task_manager


# @task(name="execute-dynamic-task", task_run_name="{task_name}")
# def execute_dynamic_task(
#     exp: Experiment,
#     task_manager: TaskManager,
#     task_name: str,
# ) -> TaskManager:
#     """Execute dynamic task."""
#     logger = get_run_logger()
#     task_manager.diagnose()
#     try:
#         logger.info(f"Starting task: {task_name}")
#         qids = [convert_qid(qid) for qid in exp.qubit_labels]
#         task_instance = task_classes[task_name]["instance"]
#         task_type = task_instance.get_task_type()
#         execution_manager = ExecutionManager.load_from_file(task_manager.calib_dir)
#         task_manager.start_all_qid_tasks(task_name, task_type, qids)
#         logger.info(f"Running task: {task_name}, id: {task_manager.id}")
#         task_manager.update_all_qid_task_status_to_running(
#             task_name=task_name, message=f"running {task_name} ...", task_type=task_type, qids=qids
#         )
#         execution_manager = execution_manager.reload().update_with_task_manager(
#             task_manager=task_manager
#         )
#         task_instance.execute(exp, task_manager)
#         execution_manager = execution_manager.reload().update_with_task_manager(
#             task_manager=task_manager
#         )
#         ExecutionHistoryDocument.update_document(execution_manager)
#         task_manager.update_all_qid_task_status_to_completed(
#             task_name=task_name, message=f"{task_name} is completed", task_type=task_type, qids=qids
#         )
#         for qid in qids:
#             executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
#             TaskHistoryDocument.upsert_document(
#                 task=executed_task, execution_manager=execution_manager
#             )
#             output_parameters = task_manager.get_output_parameter_by_task_name(
#                 task_name=task_name, task_type=task_type, qid=qid
#             )
#             if output_parameters:
#                 QubitDocument.update_calib_data(
#                     qid=qid, chip_id=execution_manager.chip_id, output_parameters=output_parameters
#                 )
#     except Exception as e:
#         logger.error(f"Failed to execute {task_name}: {e}, id: {task_manager.id}")
#         task_manager.update_all_qid_task_status_to_failed(
#             task_name=task_name, message=f"{task_name} failed", task_type=task_type, qids=qids
#         )
#         execution_manager = execution_manager.reload().update_with_task_manager(
#             task_manager=task_manager
#         )
#         raise RuntimeError(f"Task {task_name} failed: {e}")
#     finally:
#         logger.info(f"Ending task: {task_name}, id: {task_manager.id}")
#         task_manager.end_all_qid_tasks(task_name, task_type, qids)
#         task_manager.save()
#         execution_manager = execution_manager.reload().update_with_task_manager(
#             task_manager=task_manager
#         )
#         ExecutionHistoryDocument.update_document(execution_manager)
#     return task_manager
