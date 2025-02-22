from neodbmodel.execution_history import ExecutionHistoryDocument
from neodbmodel.qubit import QubitDocument
from neodbmodel.task_history import TaskHistoryDocument
from prefect import flow, get_run_logger, task
from qcflow.manager.execution import ExecutionManager
from qcflow.manager.task import CouplingTask, GlobalTask, QubitTask, TaskManager, TaskResult
from qcflow.qubex_protocols.active_protocols import task_classes
from qubex.experiment import Experiment
from repository.initialize import initialize


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


initialize()


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
        execution_id = task_manager.execution_id
        execution_manager = ExecutionManager.load_from_file(task_manager.calib_dir)
        logger.info(f"Starting task: {task_name}, execution_id: {task_manager.execution_id}")
        task_manager.start_task(task_name, task_type, qid)
        logger.info(f"Running task: {task_name}, id: {task_manager.id}")
        task_manager.update_task_status_to_running(
            task_name=task_name, message=f"running {task_name} ...", task_type=task_type, qid=qid
        )
        execution_manager = execution_manager.reload().update_with_task_manager(
            task_manager=task_manager
        )
        preprocess_result = this_task.preprocess(exp=exp, qid=qid)
        if preprocess_result is not None:
            task_manager.put_input_parameters(
                task_name=task_name,
                input_parameters=preprocess_result.input_parameters,
                task_type=task_type,
                qid=qid,
            )
            task_manager.save()
        run_result = this_task.run(exp=exp, qid=qid)
        if run_result is not None:
            postprocess_result = this_task.postprocess(
                execution_id=execution_id, run_result=run_result, qid=qid
            )
            if postprocess_result is not None:
                task_manager.put_output_parameters(
                    task_name=task_name,
                    output_parameters=postprocess_result.output_parameters,
                    task_type=task_type,
                    qid=qid,
                )
                task_manager.save_figures(
                    task_name=task_name,
                    task_type=task_type,
                    figures=postprocess_result.figures,
                    qid=qid,
                )
                task_manager.save()
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
