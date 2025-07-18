from prefect import get_run_logger, task
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow.core.calibration.execution_manager import ExecutionManager
from qdash.workflow.core.calibration.task_manager import TaskManager
from qdash.workflow.core.session.base import BaseSession
from qdash.workflow.tasks.base import BaseTask


def validate_task_name(task_names: list[str], username: str) -> list[str]:
    """Validate task names."""
    tasks = TaskDocument.find({"username": username}).run()
    task_list = [task.name for task in tasks]
    for task_name in task_names:
        if task_name not in task_list:
            raise ValueError(f"Invalid task name: {task_name}")
    return task_names


initialize()


@task(name="execute-dynamic-task")
def execute_dynamic_task_by_qid(
    session: BaseSession,
    execution_manager: ExecutionManager,
    task_manager: TaskManager,
    task_instance: BaseTask,
    qid: str,
) -> tuple[ExecutionManager, TaskManager]:
    """Execute dynamic task."""
    logger = get_run_logger()
    task_manager.diagnose()
    try:
        this_task = task_instance
        task_name = this_task.get_name()
        task_type = this_task.get_task_type()
        execution_id = task_manager.execution_id
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
        # タスクの前処理
        preprocess_result = this_task.preprocess(session=session, qid=qid)
        if preprocess_result is not None:
            task_manager.put_input_parameters(
                task_name=task_name,
                input_parameters=preprocess_result.input_parameters,
                task_type=task_type,
                qid=qid,
            )
            task_manager.save()
            execution_manager = execution_manager.update_with_task_manager(task_manager)

        # タスクの実行
        run_result = this_task.run(session=session, qid=qid)
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
                # for record tha failed result, error handling do this step
                if run_result.has_r2() and run_result.r2[qid] < this_task.r2_threshold:
                    raise ValueError(f"{this_task.name} R² value too low: {run_result.r2[qid]:.4f}")  # noqa: TRY301
                if session.name == "qubex":
                    session.update_note(
                        username=task_manager.username,
                        calib_dir=task_manager.calib_dir,
                        execution_id=execution_id,
                        task_manager_id=task_manager.id,
                    )

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
        raise RuntimeError(f"Task {task_name} failed: {e}")

    finally:
        # タスクの終了処理
        logger.info(f"Ending task: {task_name}, id: {task_manager.id}")
        task_manager.end_task(task_name, task_type, qid)
        task_manager.save()
        execution_manager = execution_manager.update_with_task_manager(task_manager)
        # 最終状態の保存
        executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
        TaskResultHistoryDocument.upsert_document(
            task=executed_task, execution_model=execution_manager.to_datamodel()
        )
        chip_doc = ChipDocument.get_current_chip(username=task_manager.username)
        ChipHistoryDocument.create_history(chip_doc)

    return execution_manager, task_manager


@task(name="execute-dynamic-task-batch")
def execute_dynamic_task_batch(
    session: BaseSession,
    execution_manager: ExecutionManager,
    task_manager: TaskManager,
    task_instance: BaseTask,
    qids: list[str],
) -> tuple[ExecutionManager, TaskManager]:
    """Execute dynamic task."""
    logger = get_run_logger()
    task_manager.diagnose()
    try:
        this_task = task_instance
        task_name = this_task.get_name()
        task_type = this_task.get_task_type()
        execution_id = task_manager.execution_id
        logger.info(f"execution manager: {execution_manager.model_dump(mode='json')}")
        logger.info(f"Starting task: {task_name}, execution_id: {task_manager.execution_id}")

        # タスク実行状態の保存
        for qid in qids:
            logger.info(f"task manager: {task_manager.model_dump(mode='json')}")
            logger.info(f"Running task: {task_name}, id: {task_manager.id}")
            task_manager.start_task(task_name, task_type, qid)
            executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
            TaskResultHistoryDocument.upsert_document(
                task=executed_task, execution_model=execution_manager.to_datamodel()
            )

        # ExecutionManagerの更新
        execution_manager = execution_manager.update_with_task_manager(task_manager)
        # タスクの前処理
        for qid in qids:
            preprocess_result = this_task.preprocess(session=session, qid=qid)
            if preprocess_result is not None:
                task_manager.put_input_parameters(
                    task_name=task_name,
                    input_parameters=preprocess_result.input_parameters,
                    task_type=task_type,
                    qid=qid,
                )
                task_manager.save()
        execution_manager = execution_manager.update_with_task_manager(task_manager)

        # タスクの実行
        run_result = this_task.batch_run(session=session, qids=qids)
        if run_result is not None:
            for qid in qids:
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
                    if run_result.has_r2() and run_result.r2[qid] < this_task.r2_threshold:
                        raise ValueError(  # noqa: TRY301
                            f"{this_task.name} R² value too low: {run_result.r2[qid]:.4f}"
                        )

                    if session.name == "qubex":
                        session.update_note(
                            username=task_manager.username,
                            calib_dir=task_manager.calib_dir,
                            execution_id=execution_id,
                            task_manager_id=task_manager.id,
                        )

        for qid in qids:
            # タスクの完了処理
            task_manager.update_task_status_to_completed(
                task_name=task_name,
                message=f"{task_name} is completed",
                task_type=task_type,
                qid=qid,
            )
            task_manager.save()
            executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
            TaskResultHistoryDocument.upsert_document(
                task=executed_task, execution_model=execution_manager.to_datamodel()
            )
        execution_manager = execution_manager.update_with_task_manager(task_manager)

        for qid in qids:
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
        raise RuntimeError(f"Task {task_name} failed: {e}")

    finally:
        # タスクの終了処理
        logger.info(f"Ending task: {task_name}, id: {task_manager.id}")
        for qid in qids:
            task_manager.end_task(task_name, task_type, qid)
            task_manager.save()
            execution_manager = execution_manager.update_with_task_manager(task_manager)

        # 最終状態の保存
        for qid in qids:
            executed_task = task_manager.get_task(task_name=task_name, task_type=task_type, qid=qid)
            TaskResultHistoryDocument.upsert_document(
                task=executed_task, execution_model=execution_manager.to_datamodel()
            )
        chip_doc = ChipDocument.get_current_chip(username=task_manager.username)
        ChipHistoryDocument.create_history(chip_doc)
    return execution_manager, task_manager
