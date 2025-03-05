from qdash.dbmodel.execution_run import ExecutionRunModel


def get_next_execution_index(date: str) -> int:
    execution_run = ExecutionRunModel.find_one({"date": date}).run()
    if execution_run:
        execution_run.index += 1
        execution_run.save()
    else:
        execution_run = ExecutionRunModel(date=date, index=1)
        execution_run.insert()
    return int(execution_run.index)
