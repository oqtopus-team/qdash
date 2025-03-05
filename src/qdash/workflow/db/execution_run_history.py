from datetime import datetime

from qdash.dbmodel.execution_run_history import ExecutionRunHistoryModel
from qdash.dbmodel.qpu import QPUModel


def insert_execution_run(
    date: str, execution_id: str, menu: dict, fridge_temperature: float, flow_url: str
) -> None:
    qpu = QPUModel.get_active_qpu()
    execution_run = ExecutionRunHistoryModel(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status="running",
        date=date,
        qpu_name=qpu.name,
        execution_id=execution_id,
        tags=menu["tags"],
        menu=menu,
        fridge_temperature=fridge_temperature,
        flow_url=flow_url,
    )
    execution_run.insert()


def update_execution_run(execution_id: str, status: str) -> None:
    execution_run = ExecutionRunHistoryModel.find_one({"execution_id": execution_id}).run()
    execution_run.status = status
    execution_run.save()
