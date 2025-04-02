import re
from datetime import datetime, timezone
from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.chip import ChipDocument

router = APIRouter()
logger = getLogger("uvicorn.app")


class Position(BaseModel):
    """Position of the qubit on the device."""

    x: float
    y: float


class MeasError(BaseModel):
    """Measurement error of the qubit."""

    prob_meas1_prep0: float
    prob_meas0_prep1: float
    readout_assignment_error: float


class QubitLifetime(BaseModel):
    """Qubit lifetime of the qubit."""

    t1: float
    t2: float


class QubitGateDuration(BaseModel):
    """Gate duration of the qubit."""

    rz: int
    sx: int
    x: int


class Qubit(BaseModel):
    """Qubit information."""

    id: int
    physical_id: int
    position: Position
    fidelity: float
    meas_error: MeasError
    qubit_lifetime: QubitLifetime
    gate_duration: QubitGateDuration


class CouplingGateDuration(BaseModel):
    """Gate duration of the coupling."""

    rzx90: int


class Coupling(BaseModel):
    """Coupling information."""

    control: int
    target: int
    fidelity: float
    gate_duration: CouplingGateDuration


class Device(BaseModel):
    """Device information."""

    name: str
    device_id: str
    qubits: list[Qubit]
    couplings: list[Coupling]
    calibrated_at: datetime


def search_coupling_data_by_control_qid(cr_params, search_term):
    filtered = {}
    for key, value in cr_params.items():
        # キーが '-' を含む場合は、左側を抽出
        left_side = key.split("-")[0] if "-" in key else key
        if left_side == search_term:
            filtered[key] = value
    return filtered


def qid_to_label(qid: str) -> str:
    """Convert a numeric qid string to a label with at least two digits. e.g. '0' -> 'Q00'."""
    if re.fullmatch(r"\d+", qid):
        return "Q" + qid.zfill(2)
    error_message = "Invalid qid format."
    raise ValueError(error_message)


def split_q_string(s):
    """ "Q31-Q29" のような文字列を "31" と "29" に分解する関数です。

    Args:
    ----
        s (str): "Q31-Q29" などの形式の文字列

    Returns:
    -------
        tuple: 分解された文字列 ("31", "29")

    Raises:
    ------
        ValueError: 入力形式が正しくない場合に発生します。

    """
    parts = s.split("-")
    if len(parts) != 2:
        raise ValueError("入力文字列の形式が正しくありません。")

    # 先頭の "Q" を除去
    left = parts[0][1:] if parts[0].startswith("Q") else parts[0]
    right = parts[1][1:] if parts[1].startswith("Q") else parts[1]

    return left, right


@router.post(
    "/device_topology",
    response_model=Device,
    summary="Get the device topology",
    description="Get the device topology.",
    operation_id="getDeviceTopology",
)
def get_device_topology(
    current_user: Annotated[User, Depends(get_current_active_user)],
    physical_qubit_index_list: list[str] = ["0", "1", "2", "3", "4", "5"],
) -> Device:
    """Get the device topology."""
    logger.info(f"current user: {current_user.username}")
    qubits = []
    couplings = []
    latest = (
        CalibrationNoteDocument.find({"task_id": "master"})
        .sort([("timestamp", -1)])  # 更新時刻で降順ソート
        .limit(1)
        .run()
    )[0]
    cr_params = latest.note["cr_params"]
    drag_hpi_params = latest.note["drag_hpi_params"]
    drag_pi_params = latest.note["drag_pi_params"]
    chip_docs = ChipDocument.find_one({"chip_id": "64Q", "username": latest.username}).run()
    # Sort physical qubit indices and create id mapping
    sorted_physical_ids = sorted(physical_qubit_index_list)
    id_mapping = {pid: idx for idx, pid in enumerate(sorted_physical_ids)}

    for qid in physical_qubit_index_list:
        x90_gate_fidelity = (chip_docs.qubits[qid].data.get("x90_gate_fidelity") or {"value": 0.5})[
            "value"
        ]
        t1 = (chip_docs.qubits[qid].data.get("t1") or {"value": 100.0})["value"]
        t2 = (chip_docs.qubits[qid].data.get("t2_echo") or {"value": 100.0})["value"]
        drag_hpi_duration = drag_hpi_params.get(qid_to_label(qid), {"duration": 20})["duration"]
        drag_pi_duration = drag_pi_params.get(qid_to_label(qid), {"duration": 20})["duration"]
        qubits.append(
            Qubit(
                id=id_mapping[qid],  # Map to new sequential id
                physical_id=int(qid),
                position=Position(
                    x=chip_docs.qubits[qid].node_info.position.x,
                    y=chip_docs.qubits[qid].node_info.position.y,
                ),
                fidelity=x90_gate_fidelity,
                meas_error=MeasError(
                    prob_meas1_prep0=0.001,
                    prob_meas0_prep1=0.001,
                    readout_assignment_error=0.001,
                ),
                qubit_lifetime=QubitLifetime(
                    t1=t1,
                    t2=t2,
                ),
                gate_duration=QubitGateDuration(
                    rz=0,
                    sx=drag_hpi_duration,
                    x=drag_pi_duration,
                ),
            )
        )

        search_result = search_coupling_data_by_control_qid(cr_params, qid_to_label(qid))
        for cr_key, cr_value in search_result.items():
            target = cr_value["target"]
            control, target = split_q_string(cr_key)
            cr_duration = cr_value.get("duration", 20)
            zx90_gate_fidelity = (
                chip_docs.couplings[f"{control}-{target}"].data.get("zx90_gate_fidelity")
                or {"value": 0.5}
            )["value"]
            couplings.append(
                Coupling(
                    control=id_mapping[control],  # Map to new sequential id
                    target=id_mapping[target],  # Map to new sequential id
                    fidelity=zx90_gate_fidelity,
                    gate_duration=CouplingGateDuration(rzx90=cr_duration),
                )
            )
    return Device(
        name="anemone",
        device_id="anemone",
        qubits=qubits,
        couplings=couplings,
        calibrated_at=datetime.now(tz=timezone.utc),
    )


# {
#   "name": "qulacs",
#   "device_id": "qiqb",
#   "qubits": [
#     {
#       "id": 0,
#       "physical_id": 0,
#       "position": {
#         "x": 0,
#         "y": 0
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 1,
#       "physical_id": 1,
#       "position": {
#         "x": 1,
#         "y": 0
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 2,
#       "physical_id": 2,
#       "position": {
#         "x": 0,
#         "y": -1
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 3,
#       "physical_id": 3,
#       "position": {
#         "x": 1,
#         "y": -1
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 4,
#       "physical_id": 4,
#       "position": {
#         "x": 2,
#         "y": 0
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 5,
#       "physical_id": 5,
#       "position": {
#         "x": 3,
#         "y": 0
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 6,
#       "physical_id": 6,
#       "position": {
#         "x": 2,
#         "y": -1
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 7,
#       "physical_id": 7,
#       "position": {
#         "x": 3,
#         "y": -1
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 8,
#       "physical_id": 8,
#       "position": {
#         "x": 4,
#         "y": 0
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 9,
#       "physical_id": 9,
#       "position": {
#         "x": 5,
#         "y": 0
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 10,
#       "physical_id": 10,
#       "position": {
#         "x": 4,
#         "y": -1
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 11,
#       "physical_id": 11,
#       "position": {
#         "x": 5,
#         "y": -1
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 12,
#       "physical_id": 12,
#       "position": {
#         "x": 6,
#         "y": 0
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 13,
#       "physical_id": 13,
#       "position": {
#         "x": 7,
#         "y": 0
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 14,
#       "physical_id": 14,
#       "position": {
#         "x": 6,
#         "y": -1
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     },
#     {
#       "id": 15,
#       "physical_id": 15,
#       "position": {
#         "x": 7,
#         "y": -1
#       },
#       "fidelity": 0.999,
#       "meas_error": {
#         "prob_meas1_prep0": 0.001,
#         "prob_meas0_prep1": 0.001,
#         "readout_assignment_error": 0.001
#       },
#       "qubit_lifetime": {
#         "t1": 100.0,
#         "t2": 100.0
#       },
#       "gate_duration": {
#         "rz": 20,
#         "sx": 20,
#         "x": 20
#       }
#     }
#   ],
#   "couplings": [
#     {
#       "control": 0,
#       "target": 2,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 0,
#       "target": 1,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 1,
#       "target": 3,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 1,
#       "target": 4,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 2,
#       "target": 3,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 3,
#       "target": 6,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 4,
#       "target": 6,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 4,
#       "target": 5,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 5,
#       "target": 7,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 5,
#       "target": 8,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 6,
#       "target": 7,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 7,
#       "target": 10,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 8,
#       "target": 10,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 8,
#       "target": 9,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 9,
#       "target": 11,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 9,
#       "target": 12,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 10,
#       "target": 11,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 11,
#       "target": 14,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 12,
#       "target": 14,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 12,
#       "target": 13,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 13,
#       "target": 15,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     },
#     {
#       "control": 14,
#       "target": 15,
#       "fidelity": 0.99,
#       "gate_duration": {
#         "cx": 40,
#         "rzx90": 40
#       }
#     }
#   ],
#   "calibrated_at": "2025-03-18 17:11:47.798353"
# }
