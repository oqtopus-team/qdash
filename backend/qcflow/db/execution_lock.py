from dbmodel.execution_lock import ExecutionLockModel
from prefect import get_run_logger


def get_execution_lock():
    item = ExecutionLockModel.find_one().run()
    return item.lock


def lock_execution():
    logger = get_run_logger()
    logger.info("Locking the execution")
    item = ExecutionLockModel.find_one().run()
    item.lock = True
    item.save()


def unlock_execution():
    logger = get_run_logger()
    logger.info("Unlocking the execution")
    item = ExecutionLockModel.find_one().run()
    item.lock = False
    item.save()
