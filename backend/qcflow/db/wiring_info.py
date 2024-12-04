from dbmodel.wiring_info import WiringInfoModel
from qcflow.schema.wiring_info import WiringInfo


def get_wiring_info() -> WiringInfo:
    wiring_info = WiringInfoModel.get_active_wiring()

    if wiring_info is None:
        raise Exception("WiringInfo is not found.")

    return WiringInfo(
        name=wiring_info.name,
        wiring_dict=wiring_info.wiring_dict.model_dump(),
    )
