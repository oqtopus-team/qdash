import uuid
from datetime import datetime
from logging import getLogger
from typing import Annotated

import dateutil.tz
import pendulum
from fastapi import APIRouter, Depends, HTTPException, Security
from prefect.client.orchestration import PrefectClient
from prefect.client.schemas.filters import (
    FlowFilter,
    FlowFilterId,
    FlowRunFilter,
    FlowRunFilterState,
    FlowRunFilterStateType,
    StateType,
)
from prefect.client.schemas.objects import Deployment
from prefect.client.schemas.schedules import construct_schedule
from prefect.states import Scheduled
from pydantic import BaseModel
from qdash.api.lib.auth import get_current_active_user, get_optional_current_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.calibration import (
    ExecuteCalibRequest,
    ExecuteCalibResponse,
    ScheduleCalibRequest,
    ScheduleCalibResponse,
)
from qdash.api.schemas.exception import InternalSeverError
from qdash.config import Settings, get_settings
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.menu import MenuDocument
from qdash.dbmodel.tag import TagDocument

router = APIRouter()
logger = getLogger("uvicorn.app")


class ScheduleCronCalibRequest(BaseModel):
    """ScheduleCronCalibRequest is a subclass of BaseModel."""

    scheduler_name: str
    menu_name: str
    cron: str
    active: bool = True


class ScheduleCronCalibResponse(BaseModel):
    """ScheduleCronCalibResponse is a subclass of BaseModel."""

    scheduler_name: str
    menu_name: str
    cron: str
    active: bool = True


class ListCronScheduleResponse(BaseModel):
    """ListCronScheduleResponse is a subclass of BaseModel."""

    schedules: list[ScheduleCronCalibResponse]


def generate_execution_id() -> str:
    """Generate a unique execution ID based on the current date and an execution index. e.g. 20220101-001.

    Returns
    -------
        str: The generated execution ID.

    """
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    execution_index = ExecutionCounterDocument.get_next_index(date_str)
    return f"{date_str}-{execution_index:03d}"


class CalibrationNoteResponse(BaseModel):
    """CalibrationNote is a subclass of BaseModel."""

    username: str
    execution_id: str
    task_id: str
    note: dict
    timestamp: str


@router.get(
    "/calibration/note",
    response_model=CalibrationNoteResponse,
    summary="Fetches all the cron schedules.",
    operation_id="listCronSchedules",
)
def get_calibration_note(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CalibrationNoteResponse:
    """Get the calibration note."""
    logger.info(f"current user: {current_user.username}")
    latest = (
        CalibrationNoteDocument.find({"task_id": "master"})
        .sort([("timestamp", -1)])  # 更新時刻で降順ソート
        .limit(1)
        .run()
    )[0]
    return CalibrationNoteResponse(
        username=latest.username,
        execution_id=latest.execution_id,
        task_id=latest.task_id,
        note=latest.note,
        timestamp=latest.timestamp,
    )


@router.get(
    "/calibration/cron-schedule",
    response_model=ListCronScheduleResponse,
    summary="Fetches all the cron schedules.",
    operation_id="listCronSchedules",
)
async def list_cron_schedules(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ListCronScheduleResponse:
    """List all the cron schedules."""
    env = settings.env
    scheduler_list = [f"cron-scheduler/{env}-cron-scheduler-{i}" for i in range(1, 4)]
    client = PrefectClient(api=settings.prefect_api_url)
    schedules = []
    for scheduler_name in scheduler_list:
        try:
            target_deployment = await client.read_deployment_by_name(scheduler_name)
        except Exception as e:
            logger.warning(e)
            raise HTTPException(status_code=404, detail="deployment not found")
        schedules.append(
            ScheduleCronCalibResponse(
                scheduler_name=scheduler_name,
                menu_name=target_deployment.parameters["menu_name"],
                cron=target_deployment.schedule.cron,  # type: ignore
                active=target_deployment.is_schedule_active,
            )
        )
    return ListCronScheduleResponse(schedules=schedules)


@router.post(
    "/calibration/cron-schedule",
    response_model=ScheduleCronCalibResponse,
    summary="Schedules a calibration with cron.",
    operation_id="scheduleCronCalib",
)
async def schedule_cron_calib(
    request: ScheduleCronCalibRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScheduleCronCalibResponse:
    """Schedule a calibration."""
    from fastapi.encoders import jsonable_encoder

    logger.warning(f"Raw request body: {jsonable_encoder(request)}")
    logger.warning(f"Request model dump: {request.model_dump()}")
    logger.warning(f"Request dict: {request.dict()}")
    logger.warning(f"Current user: {current_user.model_dump()}")
    logger.info(f"current user: {current_user.username}")
    menu = MenuDocument.find_one({"name": request.menu_name}).run()
    if menu is None:
        raise HTTPException(status_code=404, detail="menu not found")
    client = PrefectClient(api=settings.prefect_api_url)
    try:
        target_deployment = await client.read_deployment_by_name(request.scheduler_name)
    except Exception as e:
        logger.warning(e)
        raise HTTPException(status_code=404, detail="deployment not found")
    try:
        TagDocument.insert_tags(menu.tags, current_user.username)
        cron = construct_schedule(cron=request.cron, timezone="Asia/Tokyo")
        new_deployment = Deployment(
            **target_deployment.dict(),
        )
        new_deployment.schedule = cron
        new_deployment.parameters = {"menu_name": request.menu_name}
        new_deployment.is_schedule_active = request.active
        logger.info(f"flow id: {target_deployment.flow_id}")
        _ = await client.update_deployment(
            deployment=new_deployment,
            schedule=cron,
            is_schedule_active=request.active,
        )
    except Exception as e:
        logger.warning(e)
        raise InternalSeverError(detail=f"Failed to schedule calibration {e!s}")

    return ScheduleCronCalibResponse(
        scheduler_name=request.scheduler_name,
        menu_name=request.menu_name,
        cron=request.cron,
        active=request.active,
    )


@router.post(
    "/calibration",
    response_model=ExecuteCalibResponse,
    summary="Executes a calibration by creating a flow run from a deployment.",
    operation_id="execute_calib",
)
async def execute_calib(
    request: ExecuteCalibRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExecuteCalibResponse:
    """Create a flow run from a deployment."""
    client = PrefectClient(api=settings.prefect_api_url)
    logger.info(f"current user: {current_user.username}")
    env = settings.env
    target_deployment = await client.read_deployment_by_name(f"main/{env}-main")
    try:
        execution_id = generate_execution_id()
        TagDocument.insert_tags(request.tags, current_user.username)
        resp = await client.create_flow_run_from_deployment(
            deployment_id=target_deployment.id,
            parameters={"menu": request.model_dump(), "execution_id": execution_id},
        )
    except Exception as e:
        logger.warning(e)
        raise InternalSeverError(detail=f"Failed to execute calibration {e!s}")
    logger.warning(resp)
    chip_id = ChipDocument.get_current_chip(current_user.username).chip_id
    return ExecuteCalibResponse(
        flow_run_url=f"http://127.0.0.1:{settings.prefect_port}/flow-runs/flow-run/{resp.id}",
        qdash_ui_url=f"http://127.0.0.1:{settings.ui_port}/execution/{chip_id}/{execution_id}",
    )


ja = dateutil.tz.gettz("Asia/Tokyo")
local_date = datetime.now(tz=ja)


@router.post(
    "/calibration/schedule",
    summary="Schedules a calibration.",
    operation_id="schedule_calib",
)
async def schedule_calib(
    request: ScheduleCalibRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScheduleCalibResponse:
    """Schedule a calibration."""
    logger.warning(f"create menu name: {request.menu_name}")
    logger.info(f"current user: {current_user.username}")
    menu = MenuDocument.find_one({"name": request.menu_name}).run()
    if menu is None:
        raise HTTPException(status_code=404, detail="menu not found")

    # Convert MenuDocument to ExecuteCalibRequest
    menu_request = ExecuteCalibRequest(
        name=menu.name,
        chip_id=menu.chip_id,
        username=menu.username,
        description=menu.description,
        schedule=menu.schedule,
        notify_bool=menu.notify_bool,
        tasks=menu.tasks,
        task_details=menu.task_details,
        tags=menu.tags,
    )

    client = PrefectClient(api=settings.prefect_api_url)
    datetime_str = request.scheduled
    scheduled_time = datetime.fromisoformat(datetime_str)
    env = settings.env
    try:
        TagDocument.insert_tags(menu_request.tags, current_user.username)
        target_deployment = await client.read_deployment_by_name(f"main/{env}-main")
    except Exception as e:
        logger.warning(e)
        raise HTTPException(status_code=404, detail="deployment not found")
    logger.info(f"scheduled time: {scheduled_time}")
    try:
        execution_id = generate_execution_id()
        _ = await client.create_flow_run_from_deployment(
            deployment_id=target_deployment.id,
            state=Scheduled(scheduled_time=scheduled_time),
            parameters={"menu": menu_request.model_dump(), "execution_id": execution_id},
        )
    except Exception as e:
        logger.warning(e)
        raise InternalSeverError(detail=f"Failed to schedule calibration {e!s}")

    return ScheduleCalibResponse(
        menu_name=menu.name,
        description=menu.description,
        note="foo bar",
        menu=menu_request,
        timezone="Asia/Tokyo",
        scheduled_time=scheduled_time.strftime("%Y-%m-%d %H:%M:%S%z"),
        flow_run_id="",
    )


@router.get(
    "/calibration/schedule",
    response_model=list[ScheduleCalibResponse],
    summary="Fetches all the calibration schedules.",
    operation_id="fetch_all_calib_schedule",
)
async def fetch_all_calib_schedule(
    settings: Annotated[Settings, Depends] = Depends(get_settings),
    current_user: User | None = Depends(get_optional_current_user),
) -> list[ScheduleCalibResponse]:
    client = PrefectClient(api=settings.prefect_api_url)
    env = settings.env
    target_deployment = await client.read_deployment_by_name(f"main/{env}-main")
    flow_id = target_deployment.flow_id
    flowFilterId = FlowFilterId()
    flowFilterId.any_ = [flow_id]
    state = FlowRunFilterStateType()
    state.any_ = [StateType.SCHEDULED]
    flow_run_filter_state = FlowRunFilterState(type=state, name=None)

    try:
        flows = await client.read_flow_runs(
            flow_filter=FlowFilter(id=flowFilterId),
            flow_run_filter=FlowRunFilter(state=flow_run_filter_state),
        )
    except Exception as e:
        logger.warning(e)
        raise InternalSeverError(detail=f"Failed to fetch calibration schedules {e!s}")
    calib_schedules = []
    for flow in flows:
        time = flow.next_scheduled_start_time
        if time is not None:
            next_scheduled_start_time = time.in_timezone("Asia/Tokyo").strftime(
                "%Y-%m-%d %H:%M:%S%z"
            )
            calib_schedules.append(
                ScheduleCalibResponse(
                    menu_name=flow.parameters["menu"]["name"],
                    description=flow.parameters["menu"]["description"],
                    note="foo bar",
                    menu=ExecuteCalibRequest(**flow.parameters["menu"]),
                    timezone="Asia/Tokyo",
                    scheduled_time=next_scheduled_start_time,
                    flow_run_id=str(flow.id),
                )
            )
    calib_schedules = sorted(calib_schedules, key=lambda x: x.scheduled_time)
    return calib_schedules


@router.delete(
    "/calibration/schedule/{flow_run_id}",
    summary="Deletes a calibration schedule.",
    operation_id="delete_calib_schedule",
)
async def delete_calib_schedule(
    flow_run_id: str,
    settings: Annotated[Settings, Depends] = Depends(get_settings),
    current_user: User = Security(get_current_active_user),
):
    client = PrefectClient(api=settings.prefect_api_url)
    id = uuid.UUID(flow_run_id)
    try:
        await client.delete_flow_run(flow_run_id=id)
    except Exception as e:
        logger.warning(e)
        raise InternalSeverError(f"Failed to delete calibration schedule {e!s}")
