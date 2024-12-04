from dbmodel.session_info import SessionInfoModel
from lib.init_db import init_db


def init_session_info():
    init_db()
    SessionInfoModel(
        labrad_hostname="localhost",
        labrad_username="dummy",
        labrad_password="example",
        cooling_down_id="",
        experiment_username="",
        package_name="",
        active=True,
    ).insert()


def delete_session_info():
    init_db()
    SessionInfoModel.delete_all()


if __name__ == "__main__":
    init_session_info()
