import datetime
from datetime import timedelta

import pendulum
from prefect import flow
from prefect.deployments import run_deployment
from qdash.config import get_settings
from qdash.datamodel.menu import MenuModel
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.menu import MenuDocument
from zoneinfo import ZoneInfo

settings = get_settings()
env = settings.env


def generate_execution_id(username: str, chip_id: str) -> str:
    """Generate a unique execution ID based on the current date and an execution index. e.g. 20220101-001.

    Args:
    ----
        username: The username to generate the execution ID for
        chip_id: The chip ID to generate the execution ID for

    Returns:
    -------
        str: The generated execution ID.

    """
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    execution_index = ExecutionCounterDocument.get_next_index(date_str, username, chip_id)
    return f"{date_str}-{execution_index:03d}"


@flow(name="cron-scheduler", log_prints=True)
def cron_scheduler_flow(menu_name: str) -> None:
    """Scheduler flow."""
    now = datetime.datetime.now(ZoneInfo("Asia/Tokyo"))
    initialize()
    menu = MenuDocument.find_one({"name": menu_name}).run()  # type: ignore
    menu = MenuModel(
        name=menu.name,
        username=menu.username,
        backend=menu.backend,
        chip_id=menu.chip_id,
        description=menu.description,
        schedule=menu.schedule,
        notify_bool=menu.notify_bool,
        tasks=menu.tasks,
        task_details=menu.task_details,
        tags=menu.tags,
    )
    calc_min = timedelta(seconds=10)
    target = now + calc_min

    execution_id = generate_execution_id(menu.username, menu.chip_id)
    run_deployment(
        name=f"main/{env}-main",
        parameters={"menu": menu.model_dump(), "execution_id": execution_id},
        scheduled_time=target,
    )
