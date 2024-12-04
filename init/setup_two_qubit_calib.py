import random
from datetime import datetime

from dbmodel.qpu import QPUModel
from dbmodel.two_qubit_calib import (
    Data,
    EdgeInfo,
    TwoQubitCalibData,
    TwoQubitCalibModel,
)
from lib.init_db import init_db
from lib.qubit_lattice import qubit_lattice


def generate_labrad_value():
    return random.uniform(0.1, 10.0)


def generate_float_value():
    return random.uniform(0.1, 1.0)


def generate_complex_array():
    return [complex(random.uniform(-1, 1), random.uniform(-1, 1)) for _ in range(10)]


def generate_real_array():
    return [random.uniform(-1, 1) for _ in range(10)]


def generate_qubit_data():
    return TwoQubitCalibData(
        cross_resonance_power=Data(type="float_value", value=0.9, unit=""),
        average_gate_fidelity=Data(type="float_value", value=0.99, unit=""),
    )


def generate_dummy_data(edges: list[tuple]):
    qpu_name = "SAMPLE"
    data = []
    for edge in edges:
        qubit_data = TwoQubitCalibModel(
            qpu_name=qpu_name,
            cooling_down_id=1,
            label=f"Q{edge[0]}_Q{edge[1]}",
            status=random.choice(["unknown"]),
            edge_info=EdgeInfo(
                source=f"Q{edge[0]}",
                target=f"Q{edge[1]}",
                size=4,
                fill="",
            ),
            two_qubit_calib_data=generate_qubit_data(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        data.append(qubit_data)
    return data


def init_two_qubit_calib():
    init_db()
    num_qubits = 64
    nodes, edges, pos = qubit_lattice(num_qubits, 4)
    dummy_data = generate_dummy_data(edges)
    for data in dummy_data:
        data.insert()


def delete_two_qubit_calib():
    init_db()
    TwoQubitCalibModel.delete_all()


if __name__ == "__main__":
    init_two_qubit_calib()
