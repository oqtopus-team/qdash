from dbmodel.wiring_info import WiringInfoModel
from prefect import task
from qcflow.schema.menu import Menu
from qcflow.session.labrad import Session

from .util import TDM


@task(name="check sideband all")
def check_sideband_all(session):
    for key in session.connection.qube_server.list_devices():
        check_sideband(session, key[1])
    return "success"


def check_sideband(session, device_name):
    session.connection.qube_server.select_device(device_name)
    res = session.connection.qube_server.frequency_sideband()
    if "readout" in device_name or "pump" in device_name:
        flag = res == "usb"
    else:
        flag = res == "lsb"
    if not flag:
        import sys

        print(f"check {device_name} {res}", file=sys.stderr)


def create_instrument_manager(
    menu: Menu, session: Session, qubit_index_list: list[int]
) -> TDM:
    tdm = TDM(session)
    num_mux = 4
    wiring_info = WiringInfoModel.get_active_wiring_dict()
    for qubit_index in qubit_index_list:
        qubit_name = f"Q{qubit_index}"
        resonator_name = f"M{qubit_index//num_mux}"
        device_id_qubit = wiring_info["control"][qubit_name]["device_id"]
        device_id_resonator = wiring_info["readout"][resonator_name]["device_id"]

        tdm.add_qube_channel(device_id_resonator, f"Q{qubit_index}_readout")
        tdm.add_qube_channel(device_id_qubit, f"Q{qubit_index}_control")
        check_sideband(session, device_id_qubit)
        check_sideband(session, device_id_resonator)
    return tdm


@task(name="execute-experiment", task_run_name="{exp_name}", persist_result=False)
def execute_experiment(
    exp_name: str,
    tdm: TDM,
    exp: object,
    notes: dict,
    save: bool,
    savefig: bool,
    savepath: str,
    status: str,
) -> str:
    try:
        dataset = exp.take_data(tdm=tdm, notes=notes, save=save)  # type: ignore
        exp.analyze(dataset=dataset, notes=notes, savefig=savefig, savepath=savepath)  # type: ignore
        return "success"
    except Exception as e:
        raise e
