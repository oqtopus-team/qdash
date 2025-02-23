from datamodel.qubit import NodeInfoModel, PositionModel, QubitModel
from neodbmodel.chip import ChipDocument
from neodbmodel.init_qubit import qubit_lattice
from neodbmodel.initialize import initialize


def generate_qubit_data(num_qubits, pos: dict):
    qubits = {}
    for i in range(num_qubits):
        qubits[f"{i}"] = QubitModel(
            chip_id="SAMPLE",
            qid=f"{i}",
            status="pending",
            node_info=NodeInfoModel(
                position=PositionModel(
                    x=pos[i][0],
                    y=pos[i][1],
                ),
            ),
            data={},
        )
    return qubits


def init_chip_document():
    initialize()
    num_qubits = 64
    nodes, edges, pos = qubit_lattice(64, 4)
    qubits = generate_qubit_data(num_qubits, pos)
    chip = ChipDocument(
        chip_id="SAMPLE",
        size=64,
        qubits=qubits,
        couplings={},
        system_info={},
    )
    chip.save()
    return chip


if __name__ == "__main__":
    init_chip_document()
