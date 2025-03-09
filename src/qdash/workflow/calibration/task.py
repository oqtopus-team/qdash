# from neodbmodel.task import TaskDocument
from prefect import get_run_logger, task
from qdash.datamodel.task import CouplingTaskModel, GlobalTaskModel, QubitTaskModel, TaskResultModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow.manager.execution import ExecutionManager
from qdash.workflow.manager.task import TaskManager
from qdash.workflow.tasks.active_protocols import generate_task_instances
from qdash.workflow.tasks.base import BaseTask
from qubex.experiment import Experiment


def validate_task_name(task_names: list[str], username: str) -> list[str]:
    """Validate task names."""
    tasks = TaskDocument.find({"username": username}).run()
    task_list = [task.name for task in tasks]
    for task_name in task_names:
        if task_name not in task_list:
            raise ValueError(f"Invalid task name: {task_name}")
    return task_names


@task(name="build-workflow")
def build_workflow(
    task_manager: TaskManager, task_names: list[str], qubits: list[str], task_details: dict
) -> TaskManager:
    """Build workflow."""
    task_result = TaskResultModel()
    global_previous_task_id = ""
    qubit_previous_task_id = {qubit: "" for qubit in qubits}
    coupling_previous_task_id = {qubit: "" for qubit in qubits}
    task_instances = generate_task_instances(task_names=task_names, task_details=task_details)
    for name in task_names:
        if name in task_instances:
            this_task = task_instances[name]
            if this_task.is_global_task():
                task = GlobalTaskModel(name=name, upstream_id=global_previous_task_id)
                task_result.global_tasks.append(task)
                global_previous_task_id = task.task_id

            elif this_task.is_qubit_task():
                for qubit in qubits:
                    task = QubitTaskModel(
                        name=name, upstream_id=qubit_previous_task_id[qubit], qid=qubit
                    )
                    task_result.qubit_tasks.setdefault(qubit, []).append(task)
                    qubit_previous_task_id[qubit] = task.task_id
            elif this_task.is_coupling_task():
                for qubit in qubits:
                    task = CouplingTaskModel(
                        name=name, upstream_id=coupling_previous_task_id[qubit], qid=qubit
                    )
                    task_result.coupling_tasks.setdefault(qubit, []).append(task)
                    coupling_previous_task_id[qubit] = task.task_id
            else:
                raise ValueError(f"Task type {this_task.get_task_type()} not found.")
        else:
            raise ValueError(f"Task {name} not found.")
    task_manager.task_result = task_result
    return task_manager


initialize()


@task(name="execute-dynamic-task", task_run_name="{task_instance.name}")
def execute_dynamic_task_by_qid(
    exp: Experiment,
    task_manager: TaskManager,
    task_instance: BaseTask,
    qid: str,
) -> TaskManager:
    """Execute dynamic task."""
    logger = get_run_logger()
    task_manager.diagnose()
    try:
        this_task = task_instance
        task_name = this_task.get_name()
        task_type = this_task.get_task_type()
        execution_id = task_manager.execution_id
        execution_manager = ExecutionManager.load_from_file(task_manager.calib_dir)
        logger.info(f"execution manager: {execution_manager.model_dump(mode='json')}")
        logger.info(f"Starting task: {task_name}, execution_id: {task_manager.execution_id}")
        task_manager.start_task(task_name, task_type, qid)
        logger.info(f"task manager: {task_manager.model_dump(mode='json')}")
        logger.info(f"Running task: {task_name}, id: {task_manager.id}")
        # task_manager.save()
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(
            task=executed_task, execution_model=execution_manager.to_datamodel()
        )
        execution_manager = execution_manager.reload().update_with_task_manager(
            task_manager=task_manager
        )
        execution_manager.save()
        logger.info(f"execution manager: {execution_manager.model_dump()}")
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())
        preprocess_result = this_task.preprocess(exp=exp, qid=qid)
        if preprocess_result is not None:
            task_manager.put_input_parameters(
                task_name=task_name,
                input_parameters=preprocess_result.input_parameters,
                task_type=task_type,
                qid=qid,
            )
            task_manager.save()
            execution_manager = execution_manager.reload().update_with_task_manager(
                task_manager=task_manager
            )
            execution_manager.save()
            logger.info(f"execution manager: {execution_manager.model_dump()}")
            ExecutionHistoryDocument.upsert_document(
                execution_model=execution_manager.to_datamodel()
            )
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
                task_manager.save_raw_data(
                    task_name=task_name,
                    task_type=task_type,
                    raw_data=postprocess_result.raw_data,
                    qid=qid,
                )
                task_manager.save()

        task_manager.update_task_status_to_completed(
            task_name=task_name, message=f"{task_name} is completed", task_type=task_type, qid=qid
        )
        task_manager.save()
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(
            task=executed_task, execution_model=execution_manager.to_datamodel()
        )
        execution_manager = execution_manager.reload().update_with_task_manager(
            task_manager=task_manager
        )
        execution_manager.save()
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())
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
        task_manager.save()
        execution_manager = execution_manager.reload().update_with_task_manager(
            task_manager=task_manager
        )
        task_manager.update_not_executed_tasks_to_skipped(task_type=task_type, qid=qid)
        task_manager.save()
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
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(
            task=executed_task, execution_model=execution_manager.to_datamodel()
        )
    return task_manager
