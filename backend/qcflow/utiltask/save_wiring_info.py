from dbmodel.wiring_info import WiringInfoModel
from prefect import task

# from qcflow.db.wiring_info import get_wiring_info
from qcflow.schema.menu import Menu
from qcflow.session.labrad import labrad_session


@task(name="save wiring info")
def save_wiring_info(menu: Menu):
    with labrad_session() as session:
        wiring_info_name = WiringInfoModel.get_active_wiring_name()
        wiring_info = WiringInfoModel.get_active_wiring_dict()
        session.save_wiring_info(
            wiring_name=wiring_info_name,
            wiring_dict=wiring_info,
        )
