from neodbmodel.execution_history import ExecutionHistoryDocument
from neodbmodel.initialize import initialize
from pymongo import DESCENDING

if __name__ == "__main__":
    initialize()
    executions = ExecutionHistoryDocument.find(sort=[("end_at", DESCENDING)]).limit(50).run()
    print(executions)
