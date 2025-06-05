# ruff: noqa
from prefect import serve

from prefect.client.schemas.schedules import CronSchedule

from qdash.workflow.calibration.flow import serial_cal_flow
from qdash.workflow.calibration.flow import batch_cal_flow
from qdash.workflow.handler import main_flow

# from qdash.workflow.subflow.chip_info.update_props_pr import update_props_pr
from qdash.workflow.subflow.chip_info.flow import update_props

from qdash.workflow.subflow.scheduler.flow import cron_scheduler_flow
from qdash.workflow.subflow.device_gateway_integration.flow import device_gateway_integration_flow

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
    cron_scheduler_deploy_1 = cron_scheduler_flow.to_deployment(
        name=f"{deployment_name}-cron-scheduler-1",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        schedule=CronSchedule(
            cron="0 4 * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=False,
        parameters={"menu_name": "DailyCheck(TypeA)"},
    )
    cron_scheduler_deploy_2 = cron_scheduler_flow.to_deployment(
        name=f"{deployment_name}-cron-scheduler-2",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        schedule=CronSchedule(
            cron="40 4 * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=False,
        parameters={"menu_name": "DailyCheck(TypeB)"},
    )
    cron_scheduler_deploy_3 = cron_scheduler_flow.to_deployment(
        name=f"{deployment_name}-cron-scheduler-3",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        schedule=CronSchedule(
            cron="40 6 * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=False,
        parameters={"menu_name": "DailyTwoQubit"},
    )
    cron_scheduler_deploy_4 = cron_scheduler_flow.to_deployment(
        name=f"{deployment_name}-cron-scheduler-4",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        schedule=CronSchedule(
            cron="30 7 * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=False,
        parameters={"menu_name": "CheckSkew"},
    )
    cron_scheduler_deploy_5 = cron_scheduler_flow.to_deployment(
        name=f"{deployment_name}-cron-scheduler-5",
        description="""This is a scheduler.
        """,
        tags=["calibration"],
        schedule=CronSchedule(
            cron="30 8 * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=False,
        parameters={"menu_name": "CheckSkew"},
    )
    serial_cal_flow_deploy = serial_cal_flow.to_deployment(
        name=f"{deployment_name}-serial-cal-flow",
        description="""This is a cal flow.
        """,
    )
    batch_cal_flow_deploy = batch_cal_flow.to_deployment(
        name=f"{deployment_name}-batch-cal-flow",
        description="""This is a batch cal flow.
        """,
    )
    update_props_deploy = update_props.to_deployment(
        name=f"{deployment_name}-update-props",
        description="""This is a props update flow.
        """,
        tags=["system"],
        schedule=CronSchedule(
            cron="0 9 * * *",
            timezone="Asia/Tokyo",
        ),
        parameters={"username": "admin"},
        is_schedule_active=True,
    )
    device_gateway_integration_deploy = device_gateway_integration_flow.to_deployment(
        name=f"{deployment_name}-device-gateway-integration",
        description="""This is a flow to integrate the device gateway with the system.
        """,
        tags=["system"],
        parameters={
            "username": "admin",
            "request": {
                "name": "anemone",
                "device_id": "anemone",
                "qubits": [],
                "exclude_couplings": [],
                "condition": {
                    "coupling_fidelity": {"min": 0.7, "max": 1.0},
                    "qubit_fidelity": {"min": 0.9, "max": 1.0},
                    "only_maximum_connected": True,
                },
            },
        },
        schedule=CronSchedule(
            cron="18 14 * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=True,
    )

    _ = serve(
        main_deploy,  # type: ignore
        cron_scheduler_deploy_1,  # type: ignore
        cron_scheduler_deploy_2,  # type: ignore
        cron_scheduler_deploy_3,  # type: ignore
        cron_scheduler_deploy_4,  # type: ignore
        cron_scheduler_deploy_5,  # type: ignore
        serial_cal_flow_deploy,  # type: ignore
        batch_cal_flow_deploy,  # type: ignore
        update_props_deploy,  # type: ignore
        device_gateway_integration_deploy,  # type: ignore
        webserver=True,
        limit=50,
    )
