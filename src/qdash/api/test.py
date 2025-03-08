# ruff: noqa
import os
from logging import getLogger

from fastapi import APIRouter, HTTPException
from prefect.client.orchestration import PrefectClient
from prefect.client.schemas.objects import Deployment
from prefect.client.schemas.schedules import construct_schedule
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.menu import MenuDocument

initialize()

router = APIRouter(prefix="/calibration")
logger = getLogger("uvicorn.app")
prefect_host = os.getenv("PREFECT_HOST")
qdash_host = "localhost"
prefect_host = os.getenv("PREFECT_HOST")


async def main(menu_name: str, cron_str: str, env: str):
    menu = MenuDocument.find_one({"name": menu_name}).run()
    if menu is None:
        raise HTTPException(status_code=404, detail="menu not found")
    client = PrefectClient(api="http://localhost:4200")
    target_deployment = await client.read_deployment_by_name(f"cron-scheduler/{env}-scheduler")
    cron = construct_schedule(cron=cron_str, timezone="Asia/Tokyo")
    new_deployment = Deployment(
        name="cron-scheduler",
        flow_id=target_deployment.flow_id,
        schedule=cron,
        is_schedule_active=True,
        path=target_deployment.path,
        entrypoint=target_deployment.entrypoint,
        version=target_deployment.version,
        parameters={"menu_name": menu_name},
    )
    logger.info(f"flow id: {target_deployment.flow_id}")
    _ = await client.update_deployment(
        deployment=new_deployment,
        schedule=cron,
        is_schedule_active=True,
    )


if __name__ == "__main__":
    main("CheckRabi", "*/5 * * * *", "oqtopus")
