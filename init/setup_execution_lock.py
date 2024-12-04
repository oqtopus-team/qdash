from dbmodel.execution_lock import ExecutionLockModel
from lib.init_db import init_db


def init_execution_lock():
    init_db()
    ExecutionLockModel(lock=False).insert()


def delete_execution_lock():
    init_db()
    ExecutionLockModel.delete_all()


if __name__ == "__main__":
    init_execution_lock()
