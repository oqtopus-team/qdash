from prefect import serve
from prefect.client.schemas.schedules import CronSchedule
from qcflow.cal_flow import cal_flow
from qcflow.main import main_flow

# from qcflow.subflow.concurrent.flow import concurrent_flow
from qcflow.subflow.one_qubit_daily_summary.flow import one_qubit_daily_summary_flow
from qcflow.subflow.scheduler.flow import scheduler_flow
from qcflow.subflow.service_close.service_close import (
    qpu_close_flow,
    simulator_close_flow,
)
from qcflow.subflow.service_open.service_open import qpu_open_flow, simulator_open_flow

deployment_name = "oqtopus"

if __name__ == "__main__":
    main_deploy = main_flow.to_deployment(
        name=f"{deployment_name}-main",
        description="""This is a flow for E2E calibration.
        """,
        tags=["calibration"],
        parameters={
            "menu": {
                "name": "mux9-calibration",
                "description": "Single qubit calibration for mux1",
                "one_qubit_calib_plan": [
                    [0, 1, 2, 3],
                    [4, 5, 6, 7],
                    [8, 9, 10, 11],
                    [12, 13, 14, 15],
                    [16, 17, 18, 19],
                    [20, 21, 22, 23],
                    [24, 25, 26, 27],
                    [28, 29, 30, 31],
                    [32, 33, 34, 35],
                    [36, 37, 38, 39],
                    [40, 41, 42, 43],
                    [44, 45, 46, 47],
                    [48, 49, 50, 51],
                    [52, 53, 54, 55],
                    [56, 57, 58, 59],
                    [60, 61, 62, 63],
                ],
                "two_qubit_calib_plan": [[0, 5, 10, 15], [1, 6, 11, 16]],
                "notify_bool": False,
                "mode": "calib",
                "flow": [
                    "one-qubit-calibration-flow",
                ],
            }
        },
    )
    scheduler_deploy = scheduler_flow.to_deployment(
        name=f"{deployment_name}-scheduler",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        parameters={
            "menu": {
                "name": "mux1-single",
                "description": "Single qubit calibration for mux1",
                "one_qubit_calib_plan": [[1, 2, 3], [4, 5, 6]],
                "two_qubit_calib_plan": [[1, 2, 3], [4, 5, 6]],
                "notify_bool": True,
                "mode": "calib",
                "flow": [
                    "one-qubit-calibration",
                ],
            }
        },
    )
    qpu_open_deploy = qpu_open_flow.to_deployment(
        name=f"{deployment_name}-qpu-open",
        description="""Open QPU access.
        """,
        tags=["cloud"],
        schedule=CronSchedule(
            cron="0 10 * * 2",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=True,
    )
    qpu_close_deploy = qpu_close_flow.to_deployment(
        name=f"{deployment_name}-qpu-close",
        description="""Close QPU access.
        """,
        tags=["cloud"],
        schedule=CronSchedule(
            cron="0 12 * * 2",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=True,
    )
    simulator_open_deploy = simulator_open_flow.to_deployment(
        name=f"{deployment_name}-simulator-open",
        description="""Open Simulator access.
        """,
        tags=["cloud"],
        schedule=CronSchedule(
            cron="0 12 * * 1-5",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=True,
    )
    simulator_close_deploy = simulator_close_flow.to_deployment(
        name=f"{deployment_name}-simulator-close",
        description="""Close Simulator access.
        """,
        tags=["cloud"],
        schedule=CronSchedule(
            cron="0 17 * * 1-5",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=True,
    )
    one_qubit_daily_summary_deploy = one_qubit_daily_summary_flow.to_deployment(
        name=f"{deployment_name}-one-qubit-daily-summary",
        description="""This is a one-qubit-daily-summary.
        """,
        tags=["cloud"],
        schedule=CronSchedule(
            cron="*/5 * * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=True,
    )
    cal_flow_deploy = cal_flow.to_deployment(
        name=f"{deployment_name}-cal-flow",
        description="""This is a cal flow.
        """,
    )

    _ = serve(
        main_deploy,  # type: ignore
        scheduler_deploy,  # type: ignore
        qpu_open_deploy,  # type: ignore
        qpu_close_deploy,  # type: ignore
        simulator_open_deploy,  # type: ignore
        simulator_close_deploy,  # type: ignore
        one_qubit_daily_summary_deploy,  # type: ignore
        cal_flow_deploy,  # type: ignore
        webserver=True,
        limit=50,
    )
