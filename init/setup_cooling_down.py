from dbmodel.cooling_down import CoolingDownModel
from lib.init_db import init_db


def init_cooling_down():
    init_db()
    CoolingDownModel(
        cooling_down_id=1, date="2021-01-01", qpu_name="SAMPLE", size=64
    ).insert()


def delete_cooling_down():
    init_db()
    CoolingDownModel.delete_all()


if __name__ == "__main__":
    init_cooling_down()
