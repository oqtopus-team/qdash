import os
from collections import defaultdict
from io import BytesIO
from logging import getLogger
from typing import Annotated, Any, List, Optional

import matplotlib as mpl
import numpy as np
from dbmodel.execution_run_history import ExecutionRunHistoryModel
from dbmodel.one_qubit_calib import OneQubitCalibData, OneQubitCalibModel
from dbmodel.one_qubit_calib_all_history import OneQubitCalibAllHistoryModel
from dbmodel.qpu import QPUModel
from dbmodel.two_qubit_calib import TwoQubitCalibModel
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from matplotlib import pyplot as plt
from pydantic import BaseModel, Field
from pymongo import DESCENDING
from server.config import Settings, get_settings
from server.routers.execution import ExecutionRunResponse
from server.schemas.calibration import OneQubitCalibResponse, TwoQubitCalibResponse
from server.schemas.error import (
    Detail,
)

router = APIRouter()
logger = getLogger("uvicorn.app")


class QPUInfoResponse(BaseModel):
    name: str
    nodes: list[str]
    edges: list[str]
    active: bool


@router.get(
    "/qpu/figure",
    responses={404: {"model": Detail}},
    response_class=StreamingResponse,
    summary="Fetches a calibration figure by its path",
    operation_id="fetch_qpu_figure_by_path",
)
def fetch_qpu_figure_by_path(path: str):
    with open(path, "rb") as file:
        image_data = file.read()
    return StreamingResponse(BytesIO(image_data), media_type="image/png")


@router.get(
    "/qpu/info/{name}",
    response_model=QPUInfoResponse,
    operation_id="fetch_qpu_info",
)
def fetchQPUInfo(name: str):
    name = "AIST13th#14(1,0)"
    logger.warn(name)
    resp = QPUModel.find_one(QPUModel.name == name).run()
    logger.warn(resp)
    if resp is not None:
        return QPUInfoResponse(
            name=resp.name, nodes=resp.nodes, edges=resp.edges, active=resp.active
        )


@router.get(
    "/qpu",
    response_model=list[QPUInfoResponse],
    operation_id="list_qpu",
)
def list_qpu():
    resp = QPUModel.find_all(sort=[("installed_at", DESCENDING)]).run()
    return [
        QPUInfoResponse(
            name=resp.name, nodes=resp.nodes, edges=resp.edges, active=resp.active
        )
        for resp in resp
    ]


@router.get(
    "/qpu/active",
    response_model=QPUInfoResponse,
    operation_id="fetch_active_qpu",
)
def fetch_active_qpu():
    resp = QPUModel.find_one(QPUModel.active == True).run()
    return QPUInfoResponse(
        name=resp.name, nodes=resp.nodes, edges=resp.edges, active=resp.active
    )


@router.get(
    "/qpu/{name}",
    response_model=QPUInfoResponse,
    operation_id="fetch_qpu",
)
def fetch_qpu_by_name(name: str):
    resp = QPUModel.find_one(QPUModel.name == name).run()
    if resp is not None:
        return QPUInfoResponse(
            name=resp.name, nodes=resp.nodes, edges=resp.edges, active=resp.active
        )


@router.get(
    "/qpu/{name}/executions",
    response_model=list[ExecutionRunResponse],
    summary="Fetch all executions",
    operation_id="fetch_all_executions_by_qpu_name",
)
def fetch_all_executions_by_qpu_name(name: str):
    execution_runs = ExecutionRunHistoryModel.find(
        ExecutionRunHistoryModel.qpu_name == name, sort=[("timestamp", DESCENDING)]
    )
    return [
        ExecutionRunResponse(
            timestamp=execution_run.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            date=execution_run.date,
            status=execution_run.status,
            execution_id=execution_run.execution_id,
            tags=execution_run.tags,
            menu=execution_run.menu,
            qpu_name=execution_run.qpu_name,
            fridge_temperature=execution_run.fridge_temperature,
            flow_url=execution_run.flow_url,
        )
        for execution_run in execution_runs
    ]


@router.get(
    "/qpu/{name}/one_qubit_calib/nodes",
    response_model=list[OneQubitCalibResponse],
    operation_id="fetch_one_qubit_calib_by_qpu_name",
)
def fetch_one_qubit_calib_by_qpu_name(
    name: str,
    param_list: Optional[List[str]] = Query(None, alias="param_list[]"),
):
    one_qubit_calib_list = OneQubitCalibModel.find(
        OneQubitCalibModel.qpu_name == name
    ).run()
    if one_qubit_calib_list is None:
        return list[OneQubitCalibResponse]

    one_qubit_calib_resp = []
    for one_qubit_calib in one_qubit_calib_list:
        one_qubit_calib_data = one_qubit_calib.one_qubit_calib_data
        if param_list:
            filtered_data = {
                param: getattr(one_qubit_calib_data, param, None)
                for param in param_list
            }
            one_qubit_calib_data = OneQubitCalibData(**filtered_data)
        one_qubit_calib_resp.append(
            OneQubitCalibResponse(
                id=str(one_qubit_calib.id),
                qpu_name=one_qubit_calib.qpu_name,
                cooling_down_id=one_qubit_calib.cooling_down_id,
                label=one_qubit_calib.label,
                status=one_qubit_calib.status,
                node_info=one_qubit_calib.node_info,
                one_qubit_calib_data=one_qubit_calib_data,
                created_at=one_qubit_calib.created_at,
                updated_at=one_qubit_calib.updated_at,
            )
        )
    return one_qubit_calib_resp


@router.get(
    "/qpu/{name}/one_qubit_calib/nodes/{label}",
    response_model=OneQubitCalibResponse,
    operation_id="fetch_one_qubit_calib_by_label",
)
def fetch_one_qubit_calib_by_label(
    name: str,
    label: str,
    param_list: Optional[List[str]] = Query(None, alias="param_list[]"),
):
    one_qubit_calib = OneQubitCalibModel.find_one(
        OneQubitCalibModel.qpu_name == name, OneQubitCalibModel.label == label
    ).run()
    if one_qubit_calib is None:
        return OneQubitCalibResponse

    one_qubit_calib_data = one_qubit_calib.one_qubit_calib_data
    if param_list:
        filtered_data = {
            param: getattr(one_qubit_calib_data, param, None) for param in param_list
        }
        one_qubit_calib_data = OneQubitCalibData(**filtered_data)

    return OneQubitCalibResponse(
        id=str(one_qubit_calib.id),
        qpu_name=one_qubit_calib.qpu_name,
        cooling_down_id=one_qubit_calib.cooling_down_id,
        label=one_qubit_calib.label,
        status=one_qubit_calib.status,
        node_info=one_qubit_calib.node_info,
        one_qubit_calib_data=one_qubit_calib_data,
        created_at=one_qubit_calib.created_at,
        updated_at=one_qubit_calib.updated_at,
    )


class ParamData(BaseModel):
    label: str
    value: float
    unit: Optional[str] = Field(None)


class ParamResponse(BaseModel):
    param_name: str
    data: list[ParamData]


@router.get(
    "/qpu/{name}/one_qubit_calib/params/{param_name}",
    response_model=ParamResponse,
    operation_id="fetch_one_qubit_calib_by_param_name",
)
def fetch_one_qubit_calib_by_param_name(name: str, param_name: str):
    one_qubit_calib = OneQubitCalibModel.find(OneQubitCalibModel.qpu_name == name).run()
    if one_qubit_calib is None:
        return ParamResponse
    data = []
    for one_qubit_calib in one_qubit_calib:
        param = getattr(one_qubit_calib.one_qubit_calib_data, param_name, None)
        if param is None:
            continue
        data.append(
            ParamData(
                label=one_qubit_calib.label,
                value=param.value,
                unit=param.unit,
            )
        )
    return ParamResponse(param_name=param_name, data=data)


# class MetricsData(BaseModel):


class MetricsResponse(BaseModel):
    name: str
    # metrics: list[MetricsData]
    data: list[dict[str, Any]]


@router.get(
    "/qpu/{name}/history/one_qubit_calib/{param_name}",
    response_model=MetricsResponse,
    operation_id="fetch_one_qubit_calib_history_by_param_name",
)
def fetch_one_qubit_calib_history_by_param_name(
    name: str,
    param_name: str,
    tags: Optional[List[str]] = Query(None, alias="tags[]"),
):
    one_qubit_calibs = OneQubitCalibAllHistoryModel.find(
        OneQubitCalibAllHistoryModel.qpu_name == name
    ).run()
    if one_qubit_calibs is None:
        return MetricsResponse(name=param_name, data=[])

    execution_id_map: defaultdict[str, dict[str, Any]] = defaultdict(dict)
    for one_qubit_calib in one_qubit_calibs:
        if (
            tags
            and one_qubit_calib.tags
            and not any(tag in one_qubit_calib.tags for tag in tags)
        ):
            continue
        param = getattr(one_qubit_calib.one_qubit_calib_data, param_name, None)
        if param is None:
            continue
        execution_id_map[one_qubit_calib.execution_id]["event"] = (
            one_qubit_calib.execution_id
        )
        execution_id_map[one_qubit_calib.execution_id][one_qubit_calib.label] = (
            param.value
        )
    data = list(execution_id_map.values())

    return MetricsResponse(name=param_name, data=data)


@router.get(
    "/qpu/{name}/two_qubit_calib/edges",
    response_model=list[TwoQubitCalibResponse],
    operation_id="fetch_two_qubit_calib_by_qpu_name",
)
def fetch_two_qubit_calib_by_qpu_name(name: str):
    two_qubit_calib_list = TwoQubitCalibModel.find(
        TwoQubitCalibModel.qpu_name == name
    ).run()
    if two_qubit_calib_list is None:
        return list[TwoQubitCalibResponse]
    two_qubit_calib_resp = []
    for two_qubit_calib in two_qubit_calib_list:
        two_qubit_calib_resp.append(
            TwoQubitCalibResponse(
                id=str(two_qubit_calib.id),
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
    "/qpu/{name}/two_qubit_calib/edges/{label}",
    response_model=TwoQubitCalibResponse,
    operation_id="fetch_two_qubit_calib_by_label",
)
def fetch_two_qubit_calib_by_label(name: str, label: str):
    two_qubit_calib = TwoQubitCalibModel.find_one(
        TwoQubitCalibModel.qpu_name == name, TwoQubitCalibModel.label == label
    ).run()
    if two_qubit_calib is None:
        return TwoQubitCalibResponse
    return TwoQubitCalibResponse(
        id=str(two_qubit_calib.id),
        qpu_name=two_qubit_calib.qpu_name,
        cooling_down_id=two_qubit_calib.cooling_down_id,
        label=two_qubit_calib.label,
        status=two_qubit_calib.status,
        edge_info=two_qubit_calib.edge_info,
        two_qubit_calib_data=two_qubit_calib.two_qubit_calib_data,
        created_at=two_qubit_calib.created_at,
        updated_at=two_qubit_calib.updated_at,
    )


@router.get(
    "/qpu/{name}/two_qubit_calib/params/{param_name}",
    response_model=ParamResponse,
    operation_id="fetch_two_qubit_calib_by_param_name",
)
def fetch_two_qubit_calib_by_param_name(name: str, param_name: str):
    two_qubit_calib = TwoQubitCalibModel.find(TwoQubitCalibModel.qpu_name == name).run()
    if two_qubit_calib is None:
        return ParamResponse
    data = []
    for two_qubit_calib in two_qubit_calib:
        param = getattr(two_qubit_calib.two_qubit_calib_data, param_name, None)
        if param is None:
            continue
        data.append(
            ParamData(
                label=two_qubit_calib.label,
                value=param.value,
                unit=param.unit,
            )
        )
    return ParamResponse(param_name=param_name, data=data)


class Stats(BaseModel):
    average_value: float | None
    max_value: float | None
    min_value: float | None
    fig_path: str


class QPUStatsResponse(BaseModel):
    average_gate_fidelity: Stats
    resonator_frequency: Stats
    qubit_frequency: Stats
    t1: Stats
    t2_echo: Stats
    t2_star: Stats


@router.get(
    "/qpu/{name}/stats",
    response_model=QPUStatsResponse,
    operation_id="fetch_qpu_stats_by_name",
    summary="Fetch QPU stats by name",
)
def fetch_qpu_stats_by_name(
    name: str, settings: Annotated[Settings, Depends] = Depends(get_settings)
):
    def text(array: np.ndarray, ax):
        """
        dataの値をその配列のインデックスの位置で示す
        Parameters
        ----------
        array : np.ndarray
            テキストとして示す値の配列
        ax : matplotlib.axes._subplots.AxesSubplot
            値を追加したい2次元マップのaxes
        """

        for num_r, row in enumerate(array):
            for num_c, value in enumerate(array[num_r]):
                ax.text(
                    num_c,
                    num_r,
                    value,
                    color="white"
                    if (value - np.nanmin(array))
                    / (np.nanmax(array) - np.nanmin(array))
                    < 0.5
                    else "black",
                    ha="center",
                    va="center",
                    fontsize=10,
                )

    def riken_chip_sort(data_list, one_side_size):
        """
        one_side_size: チップの1辺のqubit数.
        one_side_size**2個の要素を持つ1行のリスト(data_list)を, 理研チップのqubit番号に合わせて
        [[0, 1, 4, 5, ..., ],
        [2, 3, 6, 7, ..., ],
        [...,],
        [...,],]
        の形に並べ直す.
        """

        sorted_list: list = []

        for q, data in enumerate(data_list):
            mux = q // 4
            q_res = q % 4

            if mux % (int(one_side_size / 2)) == 0 and q_res % 2 == 0:
                sorted_list.append([])

            row = (mux // (int(one_side_size / 2))) * 2 + q_res // 2

            sorted_list[row].append(data_list[q])

        return sorted_list

    path = f"{settings.qpu_data_path}/{name}"
    if not os.path.exists(path):
        os.makedirs(path)
    one_side_size = 8
    one_qubit_calibs = OneQubitCalibModel.find(
        OneQubitCalibModel.qpu_name == name
    ).run()
    # value_list = []
    value_dict: dict = {
        key: []
        for key in [
            "average_gate_fidelity",
            "resonator_frequency",
            "qubit_frequency",
            "t1",
            "t2_echo",
            "t2_star",
        ]
    }
    for one_qubit_calib in one_qubit_calibs:
        # print(r.one_qubit_calib_data.qubit_frequency_cw.value * 0.001)
        for key in value_dict.keys():
            try:
                if key == "resonator_frequency":
                    if (
                        one_qubit_calib.one_qubit_calib_data.resonator_frequency.value
                        == 0
                    ):
                        value_dict[key].append(np.nan)
                        continue
                    value_dict[key].append(
                        one_qubit_calib.one_qubit_calib_data.resonator_frequency.value
                        * 0.001
                    )
                elif key == "qubit_frequency":
                    if one_qubit_calib.one_qubit_calib_data.qubit_frequency.value == 0:
                        value_dict[key].append(np.nan)
                        continue
                    value_dict[key].append(
                        one_qubit_calib.one_qubit_calib_data.qubit_frequency.value
                        * 0.001
                    )
                elif key == "t1":
                    if one_qubit_calib.one_qubit_calib_data.t1.value == 0:
                        value_dict[key].append(np.nan)
                        continue
                    value_dict[key].append(
                        one_qubit_calib.one_qubit_calib_data.t1.value * 0.001
                    )
                elif key == "t2_echo":
                    if one_qubit_calib.one_qubit_calib_data.t2_echo.value == 0:
                        value_dict[key].append(np.nan)
                        continue
                    value_dict[key].append(
                        one_qubit_calib.one_qubit_calib_data.t2_echo.value * 0.001
                    )
                elif key == "t2_star":
                    if one_qubit_calib.one_qubit_calib_data.t2_star.value == 0:
                        value_dict[key].append(np.nan)
                        continue
                    value_dict[key].append(
                        one_qubit_calib.one_qubit_calib_data.t2_star.value * 0.001
                    )
                elif key == "average_gate_fidelity":
                    if (
                        one_qubit_calib.one_qubit_calib_data.average_gate_fidelity.value
                        == 0
                    ):
                        value_dict[key].append(np.nan)
                        continue
                    value_dict[key].append(
                        one_qubit_calib.one_qubit_calib_data.average_gate_fidelity.value
                    )
            except AttributeError as e:
                logger.error(f"Failed to get {key}: {e}")
                value_dict[key].append(np.nan)
                continue
    for key, value_list in value_dict.items():
        value_list = riken_chip_sort(value_list, one_side_size)
        plt.rcParams["figure.figsize"] = (one_side_size * 0.8, one_side_size * 0.8)
        fig, ax = plt.subplots()
        plt.tick_params(
            labelbottom=False,
            labelleft=False,
            labelright=False,
            labeltop=False,
            bottom=False,
            left=False,
            right=False,
            top=False,
        )
        ax.set_title(key)
        cmap = mpl.colormaps.get_cmap(
            "viridis"
        )  # viridis is the default colormap for imshow
        cmap.set_bad(color="white")
        im = ax.imshow(value_list, cmap=cmap)
        text(np.round(value_list, 4), ax)

        if key == "resonator_frequency":
            plt.title("Resonator frequency [GHz]")
        elif key == "qubit_frequency":
            plt.title("Qubit frequency [GHz]")
        elif key == "anharmonicity":
            plt.title("Anharmonicity [GHz]")

        # グラフ画像の保存
        plt.savefig(f"{path}/{key}.png", format="png", dpi=300)

    def safe_nanmean(array):
        return np.round(np.nanmean(array), 5) if np.any(~np.isnan(array)) else None

    def safe_nanmax(array):
        return np.round(np.nanmax(array), 5) if np.any(~np.isnan(array)) else None

    def safe_nanmin(array):
        return np.round(np.nanmin(array), 5) if np.any(~np.isnan(array)) else None

    # plt.show()
    return QPUStatsResponse(
        average_gate_fidelity=Stats(
            average_value=safe_nanmean(value_dict["average_gate_fidelity"]),
            max_value=safe_nanmax(value_dict["average_gate_fidelity"]),
            min_value=safe_nanmin(value_dict["average_gate_fidelity"]),
            fig_path=f"{path}/average_gate_fidelity.png",
        ),
        resonator_frequency=Stats(
            average_value=safe_nanmean(value_dict["resonator_frequency"]),
            max_value=safe_nanmax(value_dict["resonator_frequency"]),
            min_value=safe_nanmin(value_dict["resonator_frequency"]),
            fig_path=f"{path}/resonator_frequency.png",
        ),
        qubit_frequency=Stats(
            average_value=safe_nanmean(value_dict["qubit_frequency"]),
            max_value=safe_nanmax(value_dict["qubit_frequency"]),
            min_value=safe_nanmin(value_dict["qubit_frequency"]),
            fig_path=f"{path}/qubit_frequency.png",
        ),
        t1=Stats(
            average_value=safe_nanmean(value_dict["t1"]),
            max_value=safe_nanmax(value_dict["t1"]),
            min_value=safe_nanmin(value_dict["t1"]),
            fig_path=f"{path}/t1.png",
        ),
        t2_echo=Stats(
            average_value=safe_nanmean(value_dict["t2_echo"]),
            max_value=safe_nanmax(value_dict["t2_echo"]),
            min_value=safe_nanmin(value_dict["t2_echo"]),
            fig_path=f"{path}/t2_echo.png",
        ),
        t2_star=Stats(
            average_value=safe_nanmean(value_dict["t2_star"]),
            max_value=safe_nanmax(value_dict["t2_star"]),
            min_value=safe_nanmin(value_dict["t2_star"]),
            fig_path=f"{path}/t2_star.png",
        ),
    )
