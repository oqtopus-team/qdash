# ruff: noqa
from prefect import serve

from prefect.client.schemas.schedules import CronSchedule

from qdash.workflow.worker.flows.chip_report.flow import chip_report


from qdash.workflow.worker.flows.gateway_integration.flow import gateway_integration
from qdash.config import get_settings

settings = get_settings()
deployment_name = settings.env

if __name__ == "__main__":


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
        chip_report_deploy,  # type: ignore
        gateway_integration_deploy,  # type: ignore
        webserver=True,
        limit=50,
    )
