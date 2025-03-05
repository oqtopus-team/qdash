# ruff: noqa
from prefect import serve

# from prefect.client.schemas.schedules import CronSchedule
# from qcflow.subflow.concurrent.flow import concurrent_flow
from qdash.workflow.cal_flow import cal_flow
from qdash.workflow.main import main_flow

# from qdash.workflow.subflow.scheduler.flow import scheduler_flow
# from qdash.workflow.subflow.service_close.service_close import (
#     qpu_close_flow,
#     simulator_close_flow,
# )
# from qdash.workflow.subflow.service_open.service_open import qpu_open_flow, simulator_open_flow

deployment_name = "oqtopus"

if __name__ == "__main__":
    main_deploy = main_flow.to_deployment(
        name=f"{deployment_name}-main",
        description="""This is a flow for E2E calibration.
        """,
        tags=["calibration"],
        parameters={
            "menu": {
                "name": "mux1-single",
                "description": "Single qubit calibration for mux1",
                "qids": [["28", "29", "30", "31"]],
                "notify_bool": True,
                "tasks": [
                    "one-qubit-calibration",
                ],
            }
        },
    )
    # scheduler_deploy = scheduler_flow.to_deployment(
    #     name=f"{deployment_name}-scheduler",
    #     description="""This is a scheduler.
    #     """,
    #     tags=["calibration"],
    #     parameters={
    #         "menu": {
    #             "name": "mux1-single",
    #             "description": "Single qubit calibration for mux1",
    #             "qids": [["28", "29", "30", "31"]],
    #             "notify_bool": True,
    #             "tasks": [
    #                 "one-qubit-calibration",
    #             ],
    #         }
    #     },
    # )
    # qpu_open_deploy = qpu_open_flow.to_deployment(
    #     name=f"{deployment_name}-qpu-open",
    #     description="""Open QPU access.
    #     """,
    #     tags=["cloud"],
    #     schedule=CronSchedule(
    #         cron="0 10 * * 2",
    #         timezone="Asia/Tokyo",
    #     ),
    #     is_schedule_active=True,
    # )
    # qpu_close_deploy = qpu_close_flow.to_deployment(
    #     name=f"{deployment_name}-qpu-close",
    #     description="""Close QPU access.
    #     """,
    #     tags=["cloud"],
    #     schedule=CronSchedule(
    #         cron="0 12 * * 2",
    #         timezone="Asia/Tokyo",
    #     ),
    #     is_schedule_active=True,
    # )
    # simulator_open_deploy = simulator_open_flow.to_deployment(
    #     name=f"{deployment_name}-simulator-open",
    #     description="""Open Simulator access.
    #     """,
    #     tags=["cloud"],
    #     schedule=CronSchedule(
    #         cron="0 12 * * 1-5",
    #         timezone="Asia/Tokyo",
    #     ),
    #     is_schedule_active=True,
    # )
    # simulator_close_deploy = simulator_close_flow.to_deployment(
    #     name=f"{deployment_name}-simulator-close",
    #     description="""Close Simulator access.
    #     """,
    #     tags=["cloud"],
    #     schedule=CronSchedule(
    #         cron="0 17 * * 1-5",
    #         timezone="Asia/Tokyo",
    #     ),
    #     is_schedule_active=True,
    # )
    # one_qubit_daily_summary_deploy = one_qubit_daily_summary_flow.to_deployment(
    #     name=f"{deployment_name}-one-qubit-daily-summary",
    #     description="""This is a one-qubit-daily-summary.
    #     """,
    #     tags=["cloud"],
    #     schedule=CronSchedule(
    #         cron="*/5 * * * *",
    #         timezone="Asia/Tokyo",
    #     ),
    #     is_schedule_active=True,
    # )
    cal_flow_deploy = cal_flow.to_deployment(
        name=f"{deployment_name}-cal-flow",
        description="""This is a cal flow.
        """,
    )

    _ = serve(
        main_deploy,  # type: ignore
        # scheduler_deploy,  # type: ignore
        # qpu_open_deploy,  # type: ignore
        # qpu_close_deploy,  # type: ignore
        # simulator_open_deploy,  # type: ignore
        # simulator_close_deploy,  # type: ignore
        # one_qubit_daily_summary_deploy,  # type: ignore
        cal_flow_deploy,  # type: ignore
        webserver=True,
        limit=50,
    )
