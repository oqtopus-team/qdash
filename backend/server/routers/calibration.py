import os
import uuid
from datetime import datetime
from io import BytesIO
from logging import getLogger
from typing import Annotated, Optional

import dateutil.tz
from dbmodel.menu import MenuModel
from dbmodel.one_qubit_calib import OneQubitCalibModel
from dbmodel.one_qubit_calib_daily_summary import OneQubitCalibDailySummaryModel
from dbmodel.one_qubit_calib_history import OneQubitCalibHistoryModel
from dbmodel.qpu import QPUModel
from dbmodel.two_qubit_calib import TwoQubitCalibModel
from dbmodel.two_qubit_calib_daily_summary import TwoQubitCalibDailySummaryModel
from dbmodel.two_qubit_calib_history import TwoQubitCalibHistoryModel
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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
from server.schemas.calibration import (
    ExecuteCalibRequest,
    ExecuteCalibResponse,
    OneQubitCalibCWInfo,
    OneQubitCalibDailySummaryRequest,
    OneQubitCalibDailySummaryResponse,
    OneQubitCalibHistoryResponse,
    OneQubitCalibResponse,
    OneQubitCalibStatsRequest,
    OneQubitCalibStatsResponse,
    ScheduleCalibRequest,
    ScheduleCalibResponse,
    TwoQubitCalibDailySummaryRequest,
    TwoQubitCalibDailySummaryResponse,
    TwoQubitCalibHistoryResponse,
    TwoQubitCalibResponse,
    TwoQubitCalibStatsRequest,
    TwoQubitCalibStatsResponse,
)

# TwoQubitCalibStatsResponse,
from server.schemas.error import (
    Detail,
    NotFoundErrorResponse,
)
from server.schemas.exception import InternalSeverError
from server.schemas.success import SuccessResponse

router = APIRouter()
logger = getLogger("uvicorn.app")
prefect_host = os.getenv("PREFECT_HOST")


@router.post(
    "/calibrations",
    response_model=ExecuteCalibResponse,
    summary="Executes a calibration by creating a flow run from a deployment.",
    operation_id="execute_calib",
)
async def execute_calib(
    request: ExecuteCalibRequest,
    settings: Annotated[Settings, Depends] = Depends(get_settings),
) -> ExecuteCalibResponse:
    """
    Executes a calibration by creating a flow run from a deployment.

    Args:
        request (ExecuteCalibRequest): The request object containing the calibration data.
        settings (Settings): The application settings.

    Returns:
        FLOW_RUN_URL: The URL of the created flow run.

    Raises:
        HTTPException: If the execution of the calibration fails.
    """
    client = PrefectClient(api=settings.prefect_api_url)
    env = settings.env
    target_deployment = await client.read_deployment_by_name(f"main/{env}-main")
    try:
        resp = await client.create_flow_run_from_deployment(
            deployment_id=target_deployment.id,
            parameters={"menu": request.dict()},
        )
    except Exception as e:
        logger.warn(e)
        raise InternalSeverError(detail=f"Failed to execute calibration {str(e)}")
    logger.warn(resp)
    return ExecuteCalibResponse(
        flow_run_url=f"http://{prefect_host}:4200/flow-runs/flow-run/{resp.id}"
    )


ja = dateutil.tz.gettz("Asia/Tokyo")
local_date = datetime.now(tz=ja)


@router.post(
    "/calibrations/schedule",
    summary="Schedules a calibration.",
    operation_id="schedule_calib",
)
async def schedule_calib(
    request: ScheduleCalibRequest,
    settings: Annotated[Settings, Depends] = Depends(get_settings),
):
    logger.warn(f"create menu name: {request.menu_name}")
    menu = MenuModel.find_one(MenuModel.name == request.menu_name).run()
    if menu is None:
        raise HTTPException(status_code=404, detail="menu not found")
    execute_calib_request = ExecuteCalibRequest(
        name=menu.name,
        description=menu.description,
        one_qubit_calib_plan=menu.one_qubit_calib_plan,
        two_qubit_calib_plan=menu.two_qubit_calib_plan,
        mode=menu.mode,
        notify_bool=menu.notify_bool,
        flow=menu.flow,
        exp_list=menu.exp_list,
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
        logger.warn(e)
        raise HTTPException(status_code=404, detail="deployment not found")
    print(scheduled_time)
    try:
        _ = await client.create_flow_run_from_deployment(
            deployment_id=target_deployment.id,
            state=Scheduled(scheduled_time=scheduled_time),
            parameters={"menu": execute_calib_request.model_dump()},
        )
    except Exception as e:
        logger.warn(e)
        raise InternalSeverError(detail=f"Failed to schedule calibration {str(e)}")


@router.get(
    "/calibrations/schedule",
    response_model=list[ScheduleCalibResponse],
    summary="Fetches all the calibration schedules.",
    operation_id="fetch_all_calib_schedule",
)
async def fetch_all_calib_schedule(
    settings: Annotated[Settings, Depends] = Depends(get_settings),
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
        logger.warn(e)
        raise InternalSeverError(
            detail=f"Failed to fetch calibration schedules {str(e)}"
        )
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
    "/calibrations/schedule/{flow_run_id}",
    summary="Deletes a calibration schedule.",
    operation_id="delete_calib_schedule",
)
async def delete_calib_schedule(
    flow_run_id: str, settings: Annotated[Settings, Depends] = Depends(get_settings)
):
    client = PrefectClient(api=settings.prefect_api_url)
    id = uuid.UUID(flow_run_id)
    try:
        await client.delete_flow_run(flow_run_id=id)
    except Exception as e:
        logger.warn(e)
        raise InternalSeverError(f"Failed to delete calibration schedule {str(e)}")


@router.get(
    "/calibrations/latest/one_qubit",
    response_model=list[OneQubitCalibResponse],
    summary="Fetches all the latest one qubit calibrations.",
    operation_id="fetch_all_latest_one_qubit_calib",
)
def fetch_all_latest_one_qubit_calib() -> list[OneQubitCalibResponse]:
    """
    Fetches all the latest one qubit calibrations.

    Returns:
        A list of OneQubitCalibResponse objects representing the latest one qubit calibrations.
    """
    qpu_name = QPUModel.get_active_qpu_name()
    one_qubit_calib_list = OneQubitCalibModel.find(
        OneQubitCalibModel.qpu_name == qpu_name
    ).run()
    if one_qubit_calib_list is None:
        return list[OneQubitCalibResponse]
    one_qubit_calib_resp = []
    for one_qubit_calib in one_qubit_calib_list:
        one_qubit_calib_resp.append(
            OneQubitCalibResponse(
                qpu_name=one_qubit_calib.qpu_name,
                cooling_down_id=one_qubit_calib.cooling_down_id,
                label=one_qubit_calib.label,
                status=one_qubit_calib.status,
                node_info=one_qubit_calib.node_info,
                one_qubit_calib_data=one_qubit_calib.one_qubit_calib_data,
                created_at=one_qubit_calib.created_at,
                updated_at=one_qubit_calib.updated_at,
            )
        )
    return one_qubit_calib_resp


# @router.put(
#     "/calibrations/latest/one_qubit",
#     summary="Updates a one qubit calibration.",
#     operation_id="update_all_latest_one_qubit_calib",
# )
# def update_all_latest_one_qubit_calib(request: OneQubitCalibCWInfo):
#     logger.info(request.model_dump())


@router.put(
    "/calibrations/latest/one_qubit/cw_info",
    response_model=SuccessResponse,
    summary="Updates a one qubit calibration CW info.",
    operation_id="update_all_latest_one_qubit_calib_cw_info",
)
def update_all_latest_one_qubit_calib_cw_info(
    request: OneQubitCalibCWInfo,
) -> SuccessResponse:
    logger.info(request.model_dump())
    qpu_name = QPUModel.get_active_qpu_name()
    cw_info_dict = request.cw_info.model_dump()
    for label, cw_info in cw_info_dict.items():
        one_qubit_calib = OneQubitCalibModel.find_one(
            OneQubitCalibModel.qpu_name == qpu_name, OneQubitCalibModel.label == label
        ).run()
        if one_qubit_calib is None:
            raise
        one_qubit_calib.one_qubit_calib_data.cavity_dressed_frequency_cw = cw_info[
            "cavity_dressed_frequency_cw"
        ]
        one_qubit_calib.one_qubit_calib_data.qubit_frequency_cw = cw_info[
            "qubit_frequency_cw"
        ]
        one_qubit_calib.save()
    return SuccessResponse(message="Successfully updated CW info")


@router.get(
    "/calibrations/latest/two_qubit",
    response_model=list[TwoQubitCalibResponse],
    summary="Fetches all the latest two qubit calibrations.",
    operation_id="fetch_all_latest_two_qubit_calib",
)
def fetch_all_latest_two_qubit_calib() -> list[TwoQubitCalibResponse]:
    """
    Fetches all the latest two qubit calibrations.

    Returns:
        list: A list of TwoQubitCalibResponse objects representing the latest two qubit calibrations.
    """
    qpu_name = QPUModel.get_active_qpu_name()
    # two_qubit_calib_list = TwoQubitCalibModel.find_all().to_list()
    two_qubit_calib_list = TwoQubitCalibModel.find(
        TwoQubitCalibModel.qpu_name == qpu_name
    ).run()
    if two_qubit_calib_list is None:
        return list[TwoQubitCalibResponse]
    two_qubit_calib_resp = []
    for two_qubit_calib in two_qubit_calib_list:
        two_qubit_calib_resp.append(
            TwoQubitCalibResponse(
                qpu_name=two_qubit_calib.qpu_name,
                cooling_down_id=two_qubit_calib.cooling_down_id,
                label=two_qubit_calib.label,
                status=two_qubit_calib.status,
                edge_info=two_qubit_calib.edge_info,
                two_qubit_calib_data=two_qubit_calib.two_qubit_calib_data,
                created_at=two_qubit_calib.created_at,
                updated_at=two_qubit_calib.updated_at,
            )
        )
    return two_qubit_calib_resp


@router.get(
    "/calibrations/history/one_qubit/{label}",
    response_model=list[OneQubitCalibHistoryResponse],
    summary="Fetches the calibration history for a specific one-qubit calibration by its label.",
    operation_id="fetch_one_qubit_calib_history_by_label",
)
def fetch_one_qubit_calib_history_by_label(label: str):
    """
    Fetches the calibration history for a specific one-qubit calibration by its ID.

    Args:
        id (str): The ID of the one-qubit calibration.

    Returns:
        list[OneQubitCalibHistoryResponse]: A list of OneQubitCalibHistoryResponse objects representing the calibration history.
    """
    one_qubit_calib_histories = (
        OneQubitCalibHistoryModel.find(OneQubitCalibHistoryModel.label == label)
        .sort("date")
        .to_list()
    )
    if one_qubit_calib_histories is None:
        return list[OneQubitCalibHistoryResponse]
    one_qubit_calib_histories_resp = []
    for one_qubit_calib_history in one_qubit_calib_histories:
        one_qubit_calib_histories_resp.append(
            OneQubitCalibHistoryResponse(
                qpu_name=one_qubit_calib_history.qpu_name,
                cooling_down_id=one_qubit_calib_history.cooling_down_id,
                label=one_qubit_calib_history.label,
                date=one_qubit_calib_history.date,
                one_qubit_calib_data=one_qubit_calib_history.one_qubit_calib_data,
                created_at=one_qubit_calib_history.created_at,
                updated_at=one_qubit_calib_history.updated_at,
            )
        )
    return one_qubit_calib_histories_resp


@router.get(
    "/calibrations/history/two_qubit/{label}",
    response_model=list[TwoQubitCalibHistoryResponse],
    summary="Fetches the calibration history for a specific two-qubit calibration by its label.",
    operation_id="fetch_two_qubit_calib_history_by_label",
)
def fetch_two_qubit_calib_history_by_label(
    label: str,
) -> list[TwoQubitCalibHistoryResponse]:
    two_qubit_calib_histories = (
        TwoQubitCalibHistoryModel.find(TwoQubitCalibHistoryModel.label == label)
        .sort("date")
        .to_list()
    )
    if two_qubit_calib_histories is None:
        return list[TwoQubitCalibHistoryResponse]
    two_qubit_calib_histories_resp = []
    for two_qubit_calib_history in two_qubit_calib_histories:
        two_qubit_calib_histories_resp.append(
            TwoQubitCalibHistoryResponse(
                qpu_name=two_qubit_calib_history.qpu_name,
                cooling_down_id=two_qubit_calib_history.cooling_down_id,
                label=two_qubit_calib_history.label,
                date=two_qubit_calib_history.date,
                two_qubit_calib_data=two_qubit_calib_history.two_qubit_calib_data,
                created_at=two_qubit_calib_history.created_at,
                updated_at=two_qubit_calib_history.updated_at,
            )
        )
    return two_qubit_calib_histories_resp


@router.get(
    "/calibrations/one_qubit/summary",
    response_model=list[OneQubitCalibDailySummaryResponse],
    summary="Fetches all the one qubit calibration summaries.",
    operation_id="fetch_all_one_qubit_calib_summary",
)
def fetch_all_one_qubit_calib_summary() -> list[OneQubitCalibDailySummaryResponse]:
    one_qubit_daily_summaries = (
        OneQubitCalibDailySummaryModel.find_all()
        .sort(-OneQubitCalibDailySummaryModel.date)
        .to_list()
    )
    if one_qubit_daily_summaries is None:
        return list[OneQubitCalibDailySummaryResponse]
    one_qubit_daily_summaries_resp = []
    for one_qubit_daily_summary in one_qubit_daily_summaries:
        one_qubit_daily_summaries_resp.append(
            OneQubitCalibDailySummaryResponse(
                date=one_qubit_daily_summary.date,
                labels=one_qubit_daily_summary.labels,
                qpu_name=one_qubit_daily_summary.qpu_name,
                cooling_down_id=one_qubit_daily_summary.cooling_down_id,
                summary=one_qubit_daily_summary.summary,
                note=one_qubit_daily_summary.note,
            )
        )
    return one_qubit_daily_summaries_resp


@router.get(
    "/calibrations/two_qubit/summary",
    response_model=list[TwoQubitCalibDailySummaryResponse],
    summary="Fetches all the two qubit calibration summaries.",
    operation_id="fetch_all_two_qubit_calib_summary",
)
def fetch_all_two_qubit_calib_summary_by_date() -> (
    list[TwoQubitCalibDailySummaryResponse]
):
    two_qubit_daily_summaries = (
        TwoQubitCalibDailySummaryModel.find_all()
        .sort(-TwoQubitCalibDailySummaryModel.date)
        .to_list()
    )
    if two_qubit_daily_summaries is None:
        return list[TwoQubitCalibDailySummaryResponse]
    two_qubit_daily_summaries_resp = []
    for two_qubit_daily_summary in two_qubit_daily_summaries:
        two_qubit_daily_summaries_resp.append(
            TwoQubitCalibDailySummaryResponse(
                date=two_qubit_daily_summary.date,
                labels=two_qubit_daily_summary.labels,
                qpu_name=two_qubit_daily_summary.qpu_name,
                cooling_down_id=two_qubit_daily_summary.cooling_down_id,
                summary=two_qubit_daily_summary.summary,
                note=two_qubit_daily_summary.note,
            )
        )
    return two_qubit_daily_summaries_resp


@router.get(
    "/calibrations/one_qubit/summary/{date}",
    response_model=OneQubitCalibDailySummaryResponse,
    responses={404: {"model": Detail}},
    summary="Fetches a one qubit calibration summary by its date.",
    operation_id="fetch_one_qubit_calib_summary_by_date",
)
def fetch_one_qubit_calib_summary_by_date(
    date: str,
    field: Optional[str] = None,
) -> OneQubitCalibDailySummaryResponse | NotFoundErrorResponse:
    one_qubit_daily_summary = OneQubitCalibDailySummaryModel.find_one(
        OneQubitCalibDailySummaryModel.date == date
    ).run()
    if one_qubit_daily_summary is None:
        return NotFoundErrorResponse(
            detail=f"one qubit calibration summary for date {date} not found"
        )
    if field == "value":
        one_qubit_daily_summary.simplify()
    return OneQubitCalibDailySummaryResponse(
        date=one_qubit_daily_summary.date,
        labels=one_qubit_daily_summary.labels,
        qpu_name=one_qubit_daily_summary.qpu_name,
        cooling_down_id=one_qubit_daily_summary.cooling_down_id,
        summary=one_qubit_daily_summary.summary,
        note=one_qubit_daily_summary.note,
    )


@router.get(
    "/calibrations/two_qubit/summary/{date}",
    response_model=TwoQubitCalibDailySummaryResponse,
    responses={404: {"model": Detail}},
    summary="Fetches a two qubit calibration summary by its date.",
    operation_id="fetch_two_qubit_calib_summary_by_date",
)
def fetch_two_qubit_calib_summary_by_date(
    date: str,
) -> TwoQubitCalibDailySummaryResponse | NotFoundErrorResponse:
    two_qubit_daily_summary = TwoQubitCalibDailySummaryModel.find_one(
        TwoQubitCalibDailySummaryModel.date == date
    ).run()
    if two_qubit_daily_summary is None:
        return NotFoundErrorResponse(
            detail=f"two qubit calibration summary for date {date} not found"
        )
    return TwoQubitCalibDailySummaryResponse(
        date=two_qubit_daily_summary.date,
        labels=two_qubit_daily_summary.labels,
        qpu_name=two_qubit_daily_summary.qpu_name,
        cooling_down_id=two_qubit_daily_summary.cooling_down_id,
        summary=two_qubit_daily_summary.summary,
        note=two_qubit_daily_summary.note,
    )


@router.patch(
    "/calibrations/one_qubit/summary/{date}",
    response_model=OneQubitCalibDailySummaryResponse,
    summary="Updates a one qubit calibration summary by its date.",
    operation_id="update_one_qubit_calib_summary_by_date",
)
def update_one_qubit_calib_summary_by_date(
    date: str, request: OneQubitCalibDailySummaryRequest
) -> OneQubitCalibDailySummaryResponse | NotFoundErrorResponse:
    one_qubit_daily_summary = OneQubitCalibDailySummaryModel.find_one(
        OneQubitCalibDailySummaryModel.date == date
    ).run()
    if one_qubit_daily_summary is None:
        return NotFoundErrorResponse(
            detail=f"one qubit calibration summary for date {date} not found"
        )
    one_qubit_daily_summary.note = request.note
    one_qubit_daily_summary.save()
    return OneQubitCalibDailySummaryResponse(
        date=one_qubit_daily_summary.date,
        labels=one_qubit_daily_summary.labels,
        qpu_name=one_qubit_daily_summary.qpu_name,
        cooling_down_id=one_qubit_daily_summary.cooling_down_id,
        summary=one_qubit_daily_summary.summary,
        note=one_qubit_daily_summary.note,
    )


@router.patch(
    "/calibrations/two_qubit/summary/{date}",
    response_model=TwoQubitCalibDailySummaryModel,
    responses={404: {"model": Detail}},
    summary="Updates a two qubit calibration summary by its date.",
    operation_id="update_two_qubit_calib_summary_by_date",
)
def update_two_qubit_calib_summary_by_date(
    date: str, request: TwoQubitCalibDailySummaryRequest
) -> TwoQubitCalibDailySummaryResponse | NotFoundErrorResponse:
    two_qubit_daily_summary = TwoQubitCalibDailySummaryModel.find_one(
        TwoQubitCalibDailySummaryModel.date == date
    ).run()
    if two_qubit_daily_summary is None:
        return NotFoundErrorResponse(
            detail=f"two qubit calibration summary for date {date} not found"
        )
    two_qubit_daily_summary.note = request.note
    two_qubit_daily_summary.save()
    return TwoQubitCalibDailySummaryResponse(
        date=two_qubit_daily_summary.date,
        labels=two_qubit_daily_summary.labels,
        qpu_name=two_qubit_daily_summary.qpu_name,
        cooling_down_id=two_qubit_daily_summary.cooling_down_id,
        summary=two_qubit_daily_summary.summary,
        note=two_qubit_daily_summary.note,
    )


@router.get(
    "/calibrations/figure/{date}/{qubit}/{path}/{exp}",
    responses={404: {"model": Detail}},
    summary="Fetches a calibration figure by its date, qubit, and experiment.",
    operation_id="fetch_calib_figure_by_date",
)
def fetch_calib_figure_by_date(date: str, qubit: str, path: str, exp: str):
    def construct_file_paths(date: str, qubit: str, path: str, exp: str) -> list:
        import os

        calib_data_path = os.getenv("CALIB_DATA_PATH")
        base_path = f"{calib_data_path}/{date}/{path}"
        file_paths = [f"{base_path}/{qubit}_{exp}.png"]

        # If qubit is composed of multiple parts, generate reversed order path
        if "_" in qubit:
            qubit_parts = qubit.split("_")
            qubit_reversed = "_".join(sorted(qubit_parts, reverse=True))
            file_paths.append(f"{base_path}/{qubit_reversed}_{exp}.png")

        return file_paths

    def find_existing_file(file_paths: list[str]) -> str:
        for file_path in file_paths:
            if os.path.exists(file_path):
                return file_path
        return ""

    # Construct potential file paths
    file_paths = construct_file_paths(date, qubit, path, exp)
    # Find the first existing file
    file_path = find_existing_file(file_paths)

    if not file_path:
        # If no file is found, raise a 404 error
        raise HTTPException(
            status_code=404,
            detail=f"Figure for date {date}, qubit {qubit}, and experiment {exp} not found",
        )

    # Read and return the file
    with open(file_path, "rb") as file:
        image_data = file.read()

    return StreamingResponse(BytesIO(image_data), media_type="image/png")


@router.post(
    "/calibrations/stats/one_qubit",
    summary="Fetches one qubit calibration stats for dashboard plots.",
    response_model=list[OneQubitCalibStatsResponse],
    operation_id="fetch_one_qubit_calib_stats",
)
def fetch_one_qubit_calib_stats(
    request: OneQubitCalibStatsRequest,
) -> list[OneQubitCalibStatsResponse]:
    """
    Fetches one qubit calibration statistics for generating dashboard plots.

    Args:
        request (OneQubitCalibStatsRequest): The request object containing the labels.

    Returns:
        list: A list of dictionaries representing the calibration statistics for each date.
    """
    # from typing import Any

    # result_dict: dict[str, dict[str, Any]] = {}
    res: dict[str, OneQubitCalibStatsResponse] = {}
    for label in request.labels:
        one_qubit_calib_histories = (
            OneQubitCalibHistoryModel.find(OneQubitCalibHistoryModel.label == label)
            .sort("date")
            .to_list()
        )

        if one_qubit_calib_histories is None:
            return []

        for one_qubit_calib in one_qubit_calib_histories:
            if one_qubit_calib.one_qubit_calib_data:
                one_qubit_calib.one_qubit_calib_data.simplify()
                if one_qubit_calib.date not in res:
                    res[one_qubit_calib.date] = OneQubitCalibStatsResponse(
                        date=one_qubit_calib.date
                    )

                res[one_qubit_calib.date].add_stats(
                    one_qubit_calib.label, one_qubit_calib.one_qubit_calib_data
                )

    response_list = list(res.values())

    # Simplify the response list
    for response in response_list:
        response.simplify()

    return response_list

    # result = list(result_dict.values())

    # for r in result:
    #     # print(r)
    #     # print(r["date"])
    #     print(r.
    # return res


@router.post(
    "/calibrations/stats/two_qubit",
    summary="Fetches two qubit calibration stats for dashboard plots.",
    response_model=list[TwoQubitCalibStatsResponse],
    operation_id="fetch_two_qubit_calib_stats",
)
def fetch_two_qubit_calib_stats(
    request: TwoQubitCalibStatsRequest,
) -> list[TwoQubitCalibStatsResponse]:
    """
    Fetches two qubit calibration statistics for generating dashboard plots.

    Args:
        request (TwoQubitCalibStatsRequest): The request object containing the labels.

    Returns:
        list: A list of dictionaries representing the calibration statistics for each date.
    """

    res: dict[str, TwoQubitCalibStatsResponse] = {}
    for label in request.labels:
        two_qubit_calib_histories = (
            TwoQubitCalibHistoryModel.find(TwoQubitCalibHistoryModel.label == label)
            .sort("date")
            .to_list()
        )

        if two_qubit_calib_histories is None:
            return []

        for two_qubit_calib in two_qubit_calib_histories:
            if two_qubit_calib.two_qubit_calib_data:
                two_qubit_calib.two_qubit_calib_data.simplify()
                if two_qubit_calib.date not in res:
                    res[two_qubit_calib.date] = TwoQubitCalibStatsResponse(
                        date=two_qubit_calib.date
                    )

                res[two_qubit_calib.date].add_stats(
                    two_qubit_calib.label, two_qubit_calib.two_qubit_calib_data
                )

    response_list = list(res.values())

    # Simplify the response list
    for response in response_list:
        response.simplify()

    return response_list
