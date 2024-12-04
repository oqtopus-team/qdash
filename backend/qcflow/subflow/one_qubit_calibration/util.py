import json
from typing import Any

import numpy as np
from bunnet.exceptions import RevisionIdWasChanged
from dbmodel.one_qubit_calib import OneQubitCalibModel
from labrad.units import Value as LabradValue
from prefect import get_run_logger
from qcflow.db.mongo import (
    update_one_qubit_calibration,
    upsert_one_qubit_all_history,
    upsert_one_qubit_history,
)
from qcflow.schema.menu import Menu
from qcflow.session.labrad import Session
from qcflow.utils.slack import SlackContents, Status


class Note:
    def __init__(self):
        self.globals = {}

    def keys(self):
        pass

    def add_experiment_note(self, note_type, qubit_dict, keys, extra_param):
        pass

    def set_initial_value(self, qubit_dict, keys):
        pass

    def get_calibration_parameters(self, exp_name, output_parameters):
        return {}


class TDM:
    def __init__(self, session: Session):
        pass

    def add_qube_channel(self, device_id_resonator, qubit_name):
        pass

    pass


def input_params_to_dict(input_params: dict[str, Any]) -> dict[str, Any]:
    mydic = {}
    for key, value in input_params.items():
        if isinstance(value, LabradValue):
            mydic[key] = {
                "value": value[value.unit],
                "unit": str(value.unit),
                "type": "labrad_value",
            }
        elif isinstance(value, np.ndarray) and any(np.iscomplex(value)):
            mydic[key] = {
                "value": [value.real.tolist(), value.imag.tolist()],
                "unit": "",
                "type": "complex_array",
            }
        elif isinstance(value, np.ndarray) and (not any(np.iscomplex(value))):
            mydic[key] = {
                "value": value.tolist(),
                "unit": "",
                "type": "real_array",
            }
        elif isinstance(value, float | int):
            mydic[key] = {
                "value": value,
                "unit": "",
                "type": "float_value",
            }
        else:
            continue
    return mydic


def initialize_notes(qubit_index: int) -> dict:
    notes = {}
    qubit_name = f"Q{qubit_index}"
    json_dict = OneQubitCalibModel.get_qubit_info()[qubit_name]
    logger = get_run_logger()
    logger.info(f"json_dict: {json_dict}")
    qubit_dict = OneQubitCalibModel.convert_from_json_dict(json_dict)
    logger.info(f"qubit_dict: {qubit_dict}")
    note = Note()
    note.add_experiment_note("calibration_load", qubit_dict, qubit_dict.keys(), None)
    notes[qubit_name] = json_dict
    return notes


def send_slack_notification(menu: Menu):
    contents = SlackContents(
        status=Status.RUNNING,
        title="Start one qubit calibration for Q",
        msg="",
        notify=menu.notify_bool,
        ts="",
        path="",
    )
    ts = contents.send_slack()
    return contents, ts


def update_slack_success_notification(
    contents: SlackContents, ts: str, exp_name: str, qubit_index: int, fig_path: str
):
    contents.status = Status.SUCCESS
    contents.title = f"Success {exp_name} for Q{qubit_index}"
    contents.path = f"{fig_path}/Q{qubit_index}_{exp_name}.png"
    contents.ts = ts
    contents.send_slack()


def update_slack_failure_notification(
    contents: SlackContents, exp_name: str, qubit_index: int
):
    contents.status = Status.FAILED
    contents.title = f"Failed {exp_name} for Q{qubit_index}"
    contents.msg = "Experiment failed"
    contents.notify = True
    contents.ts = ""
    contents.path = ""
    contents.send_slack()


def handle_calibration_result(
    notes: dict,
    qubit_index: int,
    status: str,
    calib_dir: str,
    menu: Menu,
    execution_id: str,
):
    calib_result = {
        "calib_target": [qubit_index],
        "calib_notes": notes,
        "calib_result": status,
    }
    logger = get_run_logger()
    logger.info(f"calib_result: {calib_result}")
    calib_path = f"{calib_dir}/calib_full"
    logger.info(f"calib_result: {calib_result}")
    if calib_result["calib_result"] == "success":
        calibration_notes_to_json(notes=notes, path=calib_path)
        calibration_notes_to_mongo(menu=menu, notes=notes, execution_id=execution_id)
    else:
        contents = SlackContents(
            status=Status.SUCCESS,
            title=f"Success one qubit calibration for Q{qubit_index} :tada:",
            msg="",
            notify=True,
            ts="",
            path="",
        )
        contents.send_slack()


def notes_to_dict(notes: dict):
    doc = {}
    for qubit_name, note in notes.items():
        glob = note.globals
        mydic = {}
        for key in glob:
            value = glob[key].value
            if isinstance(value, LabradValue):
                mydic[key] = {
                    "value": value[value.unit],
                    "unit": str(value.unit),
                    "type": "labrad_value",
                }
            elif isinstance(value, np.ndarray) and any(np.iscomplex(value)):
                mydic[key] = {
                    "value": [value.real.tolist(), value.imag.tolist()],
                    "unit": "",
                    "type": "complex_array",
                }
            elif isinstance(value, np.ndarray) and (not any(np.iscomplex(value))):
                mydic[key] = {
                    "value": value.tolist(),
                    "unit": "",
                    "type": "real_array",
                }
            elif isinstance(value, float):
                mydic[key] = {
                    "value": value,
                    "unit": "",
                    "type": "float_value",
                }
            else:
                raise ValueError(f"invalid type {key}")
        doc[qubit_name] = mydic
    return doc


def calibration_notes_to_json(notes: dict, path: str = "./calib"):
    # notes = notes_to_dict(notes)
    for name, mydic in notes.items():
        jsonname = f"{path}/{name}.json"
        with open(jsonname, "w") as fout:
            json.dump(mydic, fout)
        print(f"output {jsonname}")


def calibration_notes_to_mongo(menu: Menu, notes: dict, execution_id: str):
    # notes = notes_to_dict(notes)
    for name, mydic in notes.items():
        update_one_qubit_calibration(name, mydic)
        try:
            upsert_one_qubit_history(menu=menu, label=name, data=mydic)
            upsert_one_qubit_all_history(
                menu=menu, label=name, data=mydic, execution_id=execution_id
            )
        except RevisionIdWasChanged as e:
            print(f"RevisionIdWasChanged: {e} name={name}")
            continue
