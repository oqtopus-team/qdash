import os
import uuid
from datetime import datetime
from logging import getLogger
from typing import Annotated, Optional

import dateutil.tz
from fastapi import APIRouter, Depends, HTTPException, Security
from neodbmodel.menu import MenuDocument
from prefect.client.orchestration import PrefectClient
from prefect.client.schemas.filters import (
    FlowFilter,
    FlowFilterId,
    FlowRunFilter,
    FlowRunFilterState,
    FlowRunFilterStateType,
    StateType,
)
from prefect.states import Scheduled
from server.config import Settings, get_settings
from server.lib.auth import get_current_active_user, get_optional_current_user
from server.schemas.auth import User
from server.schemas.calibration import (
    ExecuteCalibRequest,
    ExecuteCalibResponse,
    ScheduleCalibRequest,
    ScheduleCalibResponse,
)
from server.schemas.exception import InternalSeverError

router = APIRouter(prefix="/calibration")
logger = getLogger("uvicorn.app")
prefect_host = os.getenv("PREFECT_HOST")


@router.post(
    "/",
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
        resp = await client.create_flow_run_from_deployment(
            deployment_id=target_deployment.id,
            parameters={"menu": request.model_dump()},
        )
    except Exception as e:
        logger.warning(e)
        raise InternalSeverError(detail=f"Failed to execute calibration {e!s}")
    logger.warning(resp)
    return ExecuteCalibResponse(
        flow_run_url=f"http://{prefect_host}:4200/flow-runs/flow-run/{resp.id}"
    )


ja = dateutil.tz.gettz("Asia/Tokyo")
local_date = datetime.now(tz=ja)


@router.post(
    "/schedule",
    summary="Schedules a calibration.",
    operation_id="schedule_calib",
)
async def schedule_calib(
    request: ScheduleCalibRequest,
    settings: Annotated[Settings, Depends] = Depends(get_settings),
    current_user: User = Security(get_current_active_user),
):
    logger.warning(f"create menu name: {request.menu_name}")
    menu = MenuDocument.find_one({"name": request.menu_name}).run()
    if menu is None:
        raise HTTPException(status_code=404, detail="menu not found")

    # Convert MenuDocument to ExecuteCalibRequest
    menu_request = ExecuteCalibRequest(
        name=menu.name,
        username=menu.username,
        description=menu.description,
        qids=menu.qids,
        notify_bool=menu.notify_bool,
        tasks=menu.tasks,
        tags=menu.tags,
    )

    client = PrefectClient(api=settings.prefect_api_url)
    datetime_str = request.scheduled
    scheduled_time = datetime.fromisoformat(datetime_str)
    env = settings.env
    print(env)
    try:
        target_deployment = await client.read_deployment_by_name(f"main/{env}-main")
    except Exception as e:
        logger.warning(e)
        raise HTTPException(status_code=404, detail="deployment not found")
    print(scheduled_time)
    try:
        _ = await client.create_flow_run_from_deployment(
            deployment_id=target_deployment.id,
            state=Scheduled(scheduled_time=scheduled_time),
            parameters={"menu": menu_request.model_dump()},
        )
    except Exception as e:
        logger.warning(e)
        raise InternalSeverError(detail=f"Failed to schedule calibration {e!s}")


@router.get(
    "/schedule",
    response_model=list[ScheduleCalibResponse],
    summary="Fetches all the calibration schedules.",
    operation_id="fetch_all_calib_schedule",
)
async def fetch_all_calib_schedule(
    settings: Annotated[Settings, Depends] = Depends(get_settings),
    current_user: Optional[User] = Depends(get_optional_current_user),
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
    "/schedule/{flow_run_id}",
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
