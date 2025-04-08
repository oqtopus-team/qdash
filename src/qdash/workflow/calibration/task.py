# from neodbmodel.task import TaskDocument
import json
from pathlib import Path

from prefect import get_run_logger, task
from qdash.datamodel.task import CouplingTaskModel, GlobalTaskModel, QubitTaskModel, TaskResultModel
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow.manager.execution import ExecutionManager
from qdash.workflow.manager.task import TaskManager
from qdash.workflow.tasks.active_protocols import generate_task_instances
from qdash.workflow.tasks.base import BaseTask
from qdash.workflow.utils.merge_notes import merge_notes_by_timestamp
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
        # ExecutionManagerの取得と更新
        execution_manager = ExecutionManager(
            username=task_manager.username,
            execution_id=task_manager.execution_id,
            calib_data_path=task_manager.calib_dir,
        ).reload()
        logger.info(f"execution manager: {execution_manager.model_dump(mode='json')}")
        logger.info(f"Starting task: {task_name}, execution_id: {task_manager.execution_id}")

        # タスクの開始
        task_manager.start_task(task_name, task_type, qid)
        logger.info(f"task manager: {task_manager.model_dump(mode='json')}")
        logger.info(f"Running task: {task_name}, id: {task_manager.id}")

        # タスク実行状態の保存
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(
            task=executed_task, execution_model=execution_manager.to_datamodel()
        )

        # ExecutionManagerの更新
        execution_manager = execution_manager.update_with_task_manager(task_manager)
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())

        # タスクの前処理
        preprocess_result = this_task.preprocess(exp=exp, qid=qid)
        if preprocess_result is not None:
            task_manager.put_input_parameters(
                task_name=task_name,
                input_parameters=preprocess_result.input_parameters,
                task_type=task_type,
                qid=qid,
            )
            task_manager.save()
            execution_manager = execution_manager.update_with_task_manager(task_manager)
            ExecutionHistoryDocument.upsert_document(
                execution_model=execution_manager.to_datamodel()
            )

        # タスクの実行
        run_result = this_task.run(exp=exp, qid=qid)
        if run_result is not None:
            postprocess_result = this_task.postprocess(
                execution_id=execution_id, run_result=run_result, qid=qid
            )
            if postprocess_result is not None:
                # 出力パラメータと結果の保存
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

                # タスクのノートを取得または作成
                calib_note = json.loads(exp.calib_note.__str__())
                task_doc = CalibrationNoteDocument.find_one(
                    {
                        "execution_id": execution_id,
                        "task_id": task_manager.id,
                        "username": task_manager.username,
                    }
                ).run()

                if task_doc is None:
                    # タスクノートが存在しない場合は新規作成
                    task_doc = CalibrationNoteDocument.upsert_note(
                        username=task_manager.username,
                        execution_id=execution_id,
                        task_id=task_manager.id,
                        note=calib_note,
                    )
                else:
                    # タスクノートが存在する場合はマージ
                    merged_note = merge_notes_by_timestamp(task_doc.note, calib_note)
                    task_doc = CalibrationNoteDocument.upsert_note(
                        username=task_manager.username,
                        execution_id=execution_id,
                        task_id=task_manager.id,
                        note=merged_note,
                    )

                # JSONファイルとして出力
                note_dir = Path(f"{task_manager.calib_dir}/calib_note")
                note_dir.mkdir(parents=True, exist_ok=True)
                note_path = note_dir / f"{task_manager.id}.json"
                note_path.write_text(json.dumps(task_doc.note, indent=2))

        # タスクの完了処理
        task_manager.update_task_status_to_completed(
            task_name=task_name, message=f"{task_name} is completed", task_type=task_type, qid=qid
        )
        task_manager.save()
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(
            task=executed_task, execution_model=execution_manager.to_datamodel()
        )
        execution_manager = execution_manager.update_with_task_manager(task_manager)
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())

        # キャリブレーションデータの更新
        output_parameters = task_manager.get_output_parameter_by_task_name(
            task_name=task_name, task_type=task_type, qid=qid
        )
        logger.info(f"output_parameters: {output_parameters}")
        if output_parameters:
            if this_task.is_qubit_task():
                updated_docs = QubitDocument.update_calib_data(
                    username=task_manager.username,
                    qid=qid,
                    chip_id=execution_manager.chip_id,
                    output_parameters=output_parameters,
                )
                logger.info(f"QubitDocument updated for {updated_docs.model_dump()}")
            elif this_task.is_coupling_task():
                CouplingDocument.update_calib_data(
                    username=task_manager.username,
                    qid=qid,
                    chip_id=execution_manager.chip_id,
                    output_parameters=output_parameters,
                )
                logger.info(f"CouplingDocument updated for {qid}")

    except Exception as e:
        logger.error(f"Failed to execute {task_name}: {e}, id: {task_manager.id}")

        # エラー時の処理
        task_manager.update_task_status_to_failed(
            task_name=task_name, message=f"{task_name} failed", task_type=task_type, qid=qid
        )
        task_manager.save()
        execution_manager = execution_manager.update_with_task_manager(task_manager)
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())

        # 未実行タスクのスキップ処理
        task_manager.update_not_executed_tasks_to_skipped(task_type=task_type, qid=qid)
        task_manager.save()
        execution_manager = execution_manager.update_with_task_manager(task_manager)
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())

        raise RuntimeError(f"Task {task_name} failed: {e}")

    finally:
        # タスクの終了処理
        logger.info(f"Ending task: {task_name}, id: {task_manager.id}")
        task_manager.end_task(task_name, task_type, qid)
        task_manager.save()
        execution_manager = execution_manager.update_with_task_manager(task_manager)
        ExecutionHistoryDocument.upsert_document(execution_model=execution_manager.to_datamodel())

        # 最終状態の保存
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(
            task=executed_task, execution_model=execution_manager.to_datamodel()
        )

    return task_manager
