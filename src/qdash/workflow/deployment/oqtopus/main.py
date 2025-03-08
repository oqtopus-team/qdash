# ruff: noqa
from prefect import serve

from prefect.client.schemas.schedules import CronSchedule

# from qcflow.subflow.concurrent.flow import concurrent_flow
from qdash.workflow.calibration.flow import cal_flow
from qdash.workflow.handler import main_flow

from qdash.workflow.subflow.scheduler.flow import cron_scheduler_flow
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
    # cron_schedulers = []
    # for i in range(1,3):
    #     cron_schedulers.append(cron_scheduler_flow.to_deployment(
    #         name=f"{deployment_name}-scheduler-{i}",
    #         description="""This is a scheduler.
    #         """,
    #         tags=["calibration"],
    #         schedule=CronSchedule(
    #             cron="*/5 * * * *",
    #             timezone="Asia/Tokyo",
    #         ),
    #         is_schedule_active=False,
    #         parameters={"menu_name": "CheckRabi"},
    #     ))
    cron_scheduler_deploy_1 = cron_scheduler_flow.to_deployment(
        name=f"{deployment_name}-cron-scheduler-1",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        schedule=CronSchedule(
            cron="*/5 * * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=False,
        parameters={"menu_name": "CheckRabi"},
    )
    cron_scheduler_deploy_2 = cron_scheduler_flow.to_deployment(
        name=f"{deployment_name}-cron-scheduler-2",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        schedule=CronSchedule(
            cron="*/5 * * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=False,
        parameters={"menu_name": "CheckRabi"},
    )
    cron_scheduler_deploy_3 = cron_scheduler_flow.to_deployment(
        name=f"{deployment_name}-cron-scheduler-3",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        schedule=CronSchedule(
            cron="*/5 * * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=False,
        parameters={"menu_name": "CheckRabi"},
    )
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
        cron_scheduler_deploy_1,  # type: ignore
        cron_scheduler_deploy_2,  # type: ignore
        cron_scheduler_deploy_3,  # type: ignore
        # qpu_open_deploy,  # type: ignore
        # qpu_close_deploy,  # type: ignore
        # simulator_open_deploy,  # type: ignore
        # simulator_close_deploy,  # type: ignore
        # one_qubit_daily_summary_deploy,  # type: ignore
        cal_flow_deploy,  # type: ignore
        webserver=True,
        limit=50,
    )
