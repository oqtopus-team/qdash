from datetime import date, datetime

from prefect import get_run_logger

# from qcflow.schema.menu import Menu
from qdash.dbmodel.cooling_down import CoolingDownModel
from qdash.dbmodel.one_qubit_calib import OneQubitCalibModel, Status
from qdash.dbmodel.one_qubit_calib_all_history import OneQubitCalibAllHistoryModel
from qdash.dbmodel.one_qubit_calib_daily_summary import (
    OneQubitCalibDailySummaryModel,
    OneQubitCalibSummary,
)
from qdash.dbmodel.one_qubit_calib_history import OneQubitCalibHistoryModel
from qdash.dbmodel.one_qubit_calib_history_all import OneQubitCalibHistoryAllModel
from qdash.dbmodel.qpu import QPUModel
from qdash.dbmodel.two_qubit_calib import TwoQubitCalibModel
from qdash.dbmodel.two_qubit_calib_daily_summary import (
    TwoQubitCalibDailySummaryModel,
    TwoQubitCalibSummary,
)
from qdash.dbmodel.two_qubit_calib_history import TwoQubitCalibHistoryModel
from qdash.dbmodel.wiring_info import WiringInfoModel


def get_wiring_info(name: str):
    wiring_info = WiringInfoModel.find_one(WiringInfoModel.name == name).run()
    if wiring_info is None:
        raise
    return wiring_info.wiring_dict.dict()


def get_one_qubit_calibration(label: str):
    qpu_name = QPUModel.get_active_qpu_name()
    one_qubit = OneQubitCalibModel.find_one(
        OneQubitCalibModel.qpu_name == qpu_name, OneQubitCalibModel.label == label
    ).run()
    if one_qubit is None:
        raise
    return one_qubit.one_qubit_calib_data


def update_one_qubit_calibration(label: str, data):
    qpu_name = QPUModel.get_active_qpu_name()
    one_qubit = OneQubitCalibModel.find_one(
        OneQubitCalibModel.qpu_name == qpu_name, OneQubitCalibModel.label == label
    ).run()
    if one_qubit is None:
        raise
    one_qubit.one_qubit_calib_data = data
    one_qubit.updated_at = datetime.now()
    one_qubit.save()


def update_two_qubit_calibration(label: str, data):
    qpu_name = QPUModel.get_active_qpu_name()
    two_qubit = TwoQubitCalibModel.find_one(
        TwoQubitCalibModel.qpu_name == qpu_name, TwoQubitCalibModel.label == label
    ).run()
    if two_qubit is None:
        raise
    two_qubit.two_qubit_calib_data = data
    two_qubit.updated_at = datetime.now()
    two_qubit.save()


def update_node_status(qubit_index: int, status: Status):
    qpu_name = QPUModel.get_active_qpu_name()
    qubit_index = str(qubit_index)  # type: ignore
    if status == Status.SUCCESS:
        color = "green"
    elif status == Status.RUNNING:
        color = "blue"
    elif status == Status.FAILED:
        color = "red"
    elif status == Status.SCHEDULED:
        color = "grey"
    else:
        color = ""
    one_qubit = OneQubitCalibModel.find_one(
        OneQubitCalibModel.qpu_name == qpu_name,
        OneQubitCalibModel.label == f"Q{qubit_index}",
    )
    if one_qubit is None:
        raise
    resp = one_qubit.run()
    resp.status = status.value
    resp.node_info.fill = color
    resp.updated_at = datetime.now()
    resp.save()
    return resp


def update_edge_status(qubit_pair: list[int], status: Status):
    qpu_name = QPUModel.get_active_qpu_name()
    label = f"Q{qubit_pair[0]}_Q{qubit_pair[1]}"  # type: ignore
    if status == Status.SUCCESS:
        color = "green"
    elif status == Status.RUNNING:
        color = "blue"
    elif status == Status.FAILED:
        color = "red"
    elif status == Status.SCHEDULED:
        color = "grey"
    else:
        color = ""
    two_qubit = TwoQubitCalibModel.find_one(
        TwoQubitCalibModel.qpu_name == qpu_name, TwoQubitCalibModel.label == label
    )
    if two_qubit is None:
        raise
    resp = two_qubit.run()
    resp.status = status.value
    resp.edge_info.fill = color
    resp.updated_at = datetime.now()
    resp.save()
    return resp


def upsert_one_qubit_history(menu: Menu, label: str, data):
    qpu = QPUModel.get_active_qpu()
    one_qubit = OneQubitCalibHistoryModel.find_one(
        {"label": label, "date": date.today().strftime("%Y%m%d")}
    ).run()
    if one_qubit is None:
        one_qubit = OneQubitCalibHistoryModel(
            label=label,
            ymd=date.today().strftime("%Y%m%d"),
            qpu_name=qpu.name,
            one_qubit_calib_data=data,
            cooling_down_id=CoolingDownModel.get_latest_cooling_down_id(),
            created_at=datetime.now(),
        )

    logger = get_run_logger()
    logger.info(f"one_qubit: {one_qubit}")
    logger.info(f"data: {data}")
    one_qubit.one_qubit_calib_data = data
    one_qubit.updated_at = datetime.now()
    one_qubit.save()


def upsert_two_qubit_history(menu: Menu, label: str, data):
    qpu = QPUModel.get_active_qpu()
    two_qubit = TwoQubitCalibHistoryModel.find_one(
        {"label": label, "date": date.today().strftime("%Y%m%d")}
    ).run()
    if two_qubit is None:
        two_qubit = TwoQubitCalibHistoryModel(
            label=label,
            ymd=date.today().strftime("%Y%m%d"),
            qpu_name=qpu.name,
            two_qubit_calib_data=data,
            cooling_down_id=CoolingDownModel.get_latest_cooling_down_id(),
            created_at=datetime.now(),
        )
    from prefect import get_run_logger

    logger = get_run_logger()
    logger.info(f"two_qubit: {two_qubit}")
    logger.info(f"data: {data}")
    two_qubit.two_qubit_calib_data = data
    two_qubit.updated_at = datetime.now()
    two_qubit.save()


def upsert_one_qubit_daily_summary():
    ymd = date.today().strftime("%Y%m%d")
    resp = OneQubitCalibHistoryModel.find(OneQubitCalibHistoryModel.date == ymd)
    if len(resp.run()) == 0:
        return
    summary = []
    labels = []
    for r in resp.to_list():
        summary.append(
            OneQubitCalibSummary(
                label=r.label,
                one_qubit_calib_data=r.one_qubit_calib_data,
            )
        )
        labels.append(r.label)
        qpu_name = r.qpu_name
        cooling_down_id = r.cooling_down_id
    exsting_summary = OneQubitCalibDailySummaryModel.find_one(
        OneQubitCalibDailySummaryModel.date == ymd
    ).run()
    if exsting_summary:
        exsting_summary.summary = summary
        exsting_summary.labels = labels
        exsting_summary.save()
    else:
        one_qubit_daily_summary = OneQubitCalibDailySummaryModel(
            date=ymd,
            summary=summary,
            labels=labels,
            qpu_name=qpu_name,
            cooling_down_id=cooling_down_id,
            note="",
        )
        one_qubit_daily_summary.save()


def upsert_two_qubit_daily_summary():
    ymd = date.today().strftime("%Y%m%d")
    resp = TwoQubitCalibHistoryModel.find(TwoQubitCalibHistoryModel.date == ymd)
    if len(resp.run()) == 0:
        return
    summary = []
    labels = []
    for r in resp.to_list():
        summary.append(
            TwoQubitCalibSummary(
                label=r.label,
                two_qubit_calib_data=r.two_qubit_calib_data,
            )
        )
        labels.append(r.label)
        qpu_name = r.qpu_name
        cooling_down_id = r.cooling_down_id
    exsting_summary = TwoQubitCalibDailySummaryModel.find_one(
        TwoQubitCalibDailySummaryModel.date == ymd
    ).run()
    if exsting_summary:
        exsting_summary.summary = summary
        exsting_summary.labels = labels
        exsting_summary.save()
    else:
        two_qubit_daily_summary = TwoQubitCalibDailySummaryModel(
            date=ymd,
            summary=summary,
            labels=labels,
            qpu_name=qpu_name,
            cooling_down_id=cooling_down_id,
            note="",
        )
        two_qubit_daily_summary.save()


def get_cw_info():
    qpu_name = QPUModel.get_active_qpu_name()
    one_qubit_calib_list = OneQubitCalibModel.find(OneQubitCalibModel.qpu_name == qpu_name).run()
    # one_qubit_calib_list = OneQubitCalibModel.find_all().to_list()

    cw_info_dict = {}
    for one_qubit_calib in one_qubit_calib_list:
        cw_info_dict[one_qubit_calib.label] = one_qubit_calib.one_qubit_calib_data.dict()
    return cw_info_dict


def get_qpu(name: str = "AIST13th#14(1,0)"):
    qpu = QPUModel.find_one(QPUModel.name == name).run()
    return qpu


def get_wiring_infos():
    wiring_info = WiringInfoModel.find_one(WiringInfoModel.name == "RIKEN_CURRENT_WIRING").run()
    # print(wiring_info)
    return wiring_info


def upsert_one_qubit_history_all(menu: Menu, label: str, data):
    qpu = QPUModel.get_active_qpu()
    one_qubit = OneQubitCalibHistoryAllModel(
        label=label,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        qpu_name=qpu.name,
        one_qubit_calib_data=data,
        cooling_down_id=CoolingDownModel.get_latest_cooling_down_id(),
        created_at=datetime.now(),
    )
    logger = get_run_logger()
    logger.info(f"one_qubit: {one_qubit}")
    logger.info(f"data: {data}")
    one_qubit.one_qubit_calib_data = data
    one_qubit.updated_at = datetime.now()
    one_qubit.insert()


def upsert_one_qubit_all_history(menu: Menu, label: str, data, execution_id: str):
    qpu = QPUModel.get_active_qpu()
    one_qubit = OneQubitCalibAllHistoryModel(
        label=label,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        execution_id=execution_id,
        tags=menu.tags,
        menu=menu.model_dump(),
        qpu_name=qpu.name,
        one_qubit_calib_data=data,
        cooling_down_id=CoolingDownModel.get_latest_cooling_down_id(),
        created_at=datetime.now(),
    )
    logger = get_run_logger()
    logger.info(f"one_qubit: {one_qubit}")
    logger.info(f"data: {data}")
    one_qubit.one_qubit_calib_data = data
    one_qubit.updated_at = datetime.now()
    one_qubit.insert()
