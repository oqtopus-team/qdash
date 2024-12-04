from dbmodel.wiring_info import Wiring, WiringInfoModel
from lib.init_db import init_db


def generate_wiring():
    control = {}
    readout = {}
    for i in range(0, 64):
        control[f"Q{i}"] = {"device_id": f"device1-control_{i}"}
        readout[f"M{i//4}"] = {"device_id": f"device1-readout_{i//4}"}
    return WiringInfoModel(
        name="SAMPLE",
        wiring_dict=Wiring(control=control, readout=readout),
        active=True,
    )


def init_wiring_info():
    init_db()
    generate_wiring().insert()


def delete_wiring_info():
    init_db()
    WiringInfoModel.delete_all()


if __name__ == "__main__":
    init_wiring_info()


# {
#   "control": {
#     "Q20": {
#       "device_id": "ou2-01-control_5"
#     },
#     "Q21": {
#       "device_id": "ou2-01-control_6"
#     },
#     "Q22": {
#       "device_id": "ou2-01-control_7"
#     },
#     "Q23": {
#       "device_id": "ou2-01-control_8"
#     },
#     "Q36": {
#       "device_id": "ou3-01-control_5"
#     },
#     "Q37": {
#       "device_id": "ou3-01-control_6"
#     },
#     "Q38": {
#       "device_id": "ou3-01-control_7"
#     },
#     "Q39": {
#       "device_id": "ou3-01-control_8"
#     }
#   },
#   "readout": {
#     "M5": {
#       "device_id": "ou2-01-readout_01"
#     },
#     "M9": {
#       "device_id": "ou3-01-readout_01"
#     }
#   }
# }
