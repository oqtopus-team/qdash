from prefect import flow
from qcflow.db.mongo import upsert_one_qubit_daily_summary


@flow
def one_qubit_daily_summary_flow():
    upsert_one_qubit_daily_summary()
