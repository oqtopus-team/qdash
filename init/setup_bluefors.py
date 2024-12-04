from dbmodel.bluefors import BlueforsModel
from lib.init_db import init_db


def generate_bluefors():
    return BlueforsModel(
        id="XLD_6_1723202581.207319",
        device_id="XLD",
        timestamp="2024-08-09T11:23:01.207Z",
        resistance=12481.232,
        reactance=863037.4,
        temperature=0.010865,
        rez=12478.622,
        imz=180.465,
        magnitude=12479.927,
        angle=89.171,
        channel_nr=6,
    )


def get_latest_temperature(device_id, channel_nr):
    latest_record = BlueforsModel.find_one(
        BlueforsModel.device_id == device_id,
        BlueforsModel.channel_nr == channel_nr,
        sort=[("timestamp", -1)],
    ).run()
    return latest_record


def init_bluefors():
    init_db()
    generate_bluefors().insert()


def delete_bluefors():
    init_db()
    BlueforsModel.delete_all()


if __name__ == "__main__":
    init_bluefors()
