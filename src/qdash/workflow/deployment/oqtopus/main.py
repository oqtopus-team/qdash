# ruff: noqa
from prefect import serve

from prefect.client.schemas.schedules import CronSchedule

from qdash.workflow.core.calibration.flow import serial_cal_flow
from qdash.workflow.core.calibration.flow import batch_cal_flow
from qdash.workflow.entrypoints.handler import main_flow

from qdash.workflow.worker.flows.chip_report.flow import chip_report

from qdash.workflow.worker.flows.scheduler.flow import cron_scheduler_flow
from qdash.workflow.worker.flows.gateway_integration.flow import gateway_integration
from qdash.workflow.examples.repeat_rabi_parallel import repeat_rabi_parallel
from qdash.config import get_settings

settings = get_settings()
deployment_name = settings.env

if __name__ == "__main__":
    repeat_rabi_parallel_deploy = repeat_rabi_parallel.to_deployment(
        name="repeat-rabei",
        description="S",
        tags=["example", "python-flow"],
        parameters={
            "username": "orangekame3",
            "chip_id": "64Qv3",
            "qids": ["32", "38"],
        },
    )
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
    chip_report_deploy = chip_report.to_deployment(
        name=f"{deployment_name}-chip-report",
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
    gateway_integration_deploy = gateway_integration.to_deployment(
        name=f"{deployment_name}-gateway-integration",
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
                    "coupling_fidelity": {"min": 0.7, "max": 1.0, "is_within_24h": True},
                    "qubit_fidelity": {"min": 0.9, "max": 1.0, "is_within_24h": False},
                    "readout_fidelity": {"min": 0.6, "max": 1.0, "is_within_24h": True},
                    "only_maximum_connected": True,
                },
            },
        },
        schedule=CronSchedule(
            cron="5 9 * * *",
            timezone="Asia/Tokyo",
        ),
        is_schedule_active=True,
    )

    _ = serve(
        repeat_rabi_parallel_deploy,
        main_deploy,  # type: ignore
        cron_scheduler_deploy_1,  # type: ignore
        cron_scheduler_deploy_2,  # type: ignore
        cron_scheduler_deploy_3,  # type: ignore
        cron_scheduler_deploy_4,  # type: ignore
        cron_scheduler_deploy_5,  # type: ignore
        serial_cal_flow_deploy,  # type: ignore
        batch_cal_flow_deploy,  # type: ignore
        chip_report_deploy,  # type: ignore
        gateway_integration_deploy,  # type: ignore
        webserver=True,
        limit=50,
    )
