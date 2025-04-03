import logging
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.logger import logger
from pydantic import BaseModel
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.chip import ChipDocument

router = APIRouter()
gunicorn_logger = logging.getLogger("gunicorn.error")
logger.handlers = gunicorn_logger.handlers
if __name__ != "main":
    logger.setLevel(gunicorn_logger.level)
else:
    logger.setLevel(logging.DEBUG)


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


def search_coupling_data_by_control_qid(cr_params: dict, search_term: str) -> dict:
    """Search for coupling data by control qubit id."""
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


def split_q_string(cr_label: str) -> tuple[str, str]:
    """Split a string of the form "Q31-Q29" into two parts.

    Args:
    ----
        cr_label (str): "Q31-Q29" string.

    Returns:
    -------
        tuple: example ("31", "29") or ("4", "5") if the string is in the correct format.
               Leading zeros are removed.

    Raises:
    ------
        ValueError: If the input string is not in the correct format.

    """
    parts = cr_label.split("-")
    expected_parts_count = 2
    error_message = "Invalid format. Expected 'Q31-Q29' or 'Q31-Q29'."
    if len(parts) != expected_parts_count:
        raise ValueError(error_message)

    # Remove the leading 'Q' if present and convert to integer to remove leading zeros
    left = parts[0][1:] if parts[0].startswith("Q") else parts[0]
    right = parts[1][1:] if parts[1].startswith("Q") else parts[1]

    # Convert to integer to remove leading zeros, then back to string
    left = str(int(left))
    right = str(int(right))

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
        CalibrationNoteDocument.find({"task_id": "master"}).sort([("timestamp", -1)]).limit(1).run()
    )[0]
    cr_params = latest.note["cr_params"]
    drag_hpi_params = latest.note["drag_hpi_params"]
    drag_pi_params = latest.note["drag_pi_params"]
    chip_docs = ChipDocument.find_one({"chip_id": "64Q", "username": latest.username}).run()
    # Sort physical qubit indices and create id mapping
    sorted_physical_ids = sorted(physical_qubit_index_list)
    id_mapping = {pid: idx for idx, pid in enumerate(sorted_physical_ids)}
    logger.info(f"id_mapping: {id_mapping}")

    for qid in physical_qubit_index_list:
        x90_gate_fidelity = (chip_docs.qubits[qid].data.get("x90_gate_fidelity") or {"value": 0.5})[
            "value"
        ]
        t1 = (chip_docs.qubits[qid].data.get("t1") or {"value": 100.0})["value"]
        t2 = (chip_docs.qubits[qid].data.get("t2_echo") or {"value": 100.0})["value"]
        drag_hpi_duration = drag_hpi_params.get(qid_to_label(qid), {"duration": 20})["duration"]
        drag_pi_duration = drag_pi_params.get(qid_to_label(qid), {"duration": 20})["duration"]
        readout_fidelity_0 = (
            chip_docs.qubits[qid].data.get("readout_fidelity_0") or {"value": 0.5}
        )["value"]
        readout_fidelity_1 = (
            chip_docs.qubits[qid].data.get("readout_fidelity_1") or {"value": 0.5}
        )["value"]
        # Calculate readout assignment error
        prob_meas1_prep0 = 1 - readout_fidelity_0
        prob_meas0_prep1 = 1 - readout_fidelity_1
        # Calculate readout assignment error
        readout_assignment_error = 1 - (readout_fidelity_0 + readout_fidelity_1) / 2

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
                    prob_meas1_prep0=prob_meas1_prep0,
                    prob_meas0_prep1=prob_meas0_prep1,
                    readout_assignment_error=readout_assignment_error,
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
            # Only append if both control and target qubits exist in id_mapping
            if control in id_mapping and target in id_mapping:
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
