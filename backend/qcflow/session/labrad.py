import contextlib

from dbmodel.session_info import SessionInfoModel
from prefect import get_run_logger


class QubeServer:
    def select_device(self, device_name):
        pass

    def frequency_sideband(self):
        pass

    def list_devices(self):
        # 実際の実装をここに追加
        return ["device1"]


class Connection:
    def __init__(self):
        self.qube_server = QubeServer()

    def disconnect(self):
        pass


class Session(object):
    labrad_hostname: str
    labrad_username: str
    labrad_password: str
    cooling_down_id: str
    experiment_username: str
    package_name: str
    connection: Connection

    def __init__(
        self,
        labrad_hostname,
        labrad_username,
        labrad_password,
        cooling_down_id,
        experiment_username,
        package_name,
    ):
        self.labrad_hostname = labrad_hostname
        self.labrad_username = labrad_username
        self.labrad_password = labrad_password
        self.cooling_down_id = cooling_down_id
        self.experiment_username = experiment_username
        self.package_name = package_name
        self.connection = Connection()

    def save_wiring_info(self, wiring_name, wiring_dict):
        pass


@contextlib.contextmanager
def labrad_session():
    logger = get_run_logger()
    logger.info("session connected!")
    session_info = SessionInfoModel.get_active_session_info()
    session = Session(
        labrad_hostname=session_info.labrad_hostname,
        labrad_username=session_info.labrad_username,
        labrad_password=session_info.labrad_password,
        cooling_down_id=session_info.cooling_down_id,
        experiment_username=session_info.experiment_username,
        package_name=session_info.package_name,
    )
    try:
        yield session
    finally:
        session.connection.disconnect()
        logger.info("session disconnected!")
