import random
from datetime import datetime

from dbmodel.one_qubit_calib import (
    Data,
    NodeInfo,
    OneQubitCalibData,
    OneQubitCalibModel,
    Position,
)
from lib.init_db import init_db
from lib.qubit_lattice import qubit_lattice


def generate_labrad_value():
    return random.uniform(0.1, 10.0)


def generate_float_value():
    return random.uniform(0.89, 0.99)


def generate_qubit_data():
    return OneQubitCalibData(
        resonator_frequency=Data(
            type="labrad_value", value=random.uniform(5500, 6000), unit="MHz"
        ),
        qubit_frequency=Data(
            type="labrad_value", value=random.uniform(4000, 5000), unit="MHz"
        ),
        t1=Data(type="float_value", value=random.uniform(20000, 40000), unit="ns"),
        t2_star=Data(type="float_value", value=random.uniform(10000, 20000), unit="ns"),
        t2_echo=Data(type="float_value", value=random.uniform(10000, 20000), unit="ns"),
        average_gate_fidelity=Data(
            type="float_value", value=generate_float_value(), unit=""
        ),
    )


def generate_dummy_data(num_qubits, pos: dict):
    qpu_name = "SAMPLE"  # QPUModel.get_active_qpu_name()
    data = []
    for i in range(num_qubits):
        qubit_data = OneQubitCalibModel(
            qpu_name=qpu_name,
            cooling_down_id=1,
            label=f"Q{i}",
            status=random.choice(["unknown"]),
            node_info=NodeInfo(
                fill="",
                position=Position(
                    x=pos[i][0],
                    y=pos[i][1],
                ),
            ),
            one_qubit_calib_data=generate_qubit_data(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        data.append(qubit_data)
    return data


def delete_one_qubit_calib():
    init_db()
    OneQubitCalibModel.delete_all()


def init_one_qubit_calib():
    init_db()
    num_qubits = 64
    nodes, edges, pos = qubit_lattice(64, 4)
    dummy_data = generate_dummy_data(num_qubits, pos)
    for data in dummy_data:
        data.insert()


if __name__ == "__main__":
    init_one_qubit_calib()
