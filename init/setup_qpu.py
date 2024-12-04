from datetime import datetime

from dbmodel.qpu import (
    QPUModel,
)
from lib.init_db import init_db
from lib.qubit_lattice import qubit_lattice

nodes, edges, pos = qubit_lattice(64, 4)

new_nodes = []
for i in nodes:
    new_nodes.append(f"Q{i}")

new_edges = []
for t in edges:
    for j in range(len(t) - 1):
        new_edges.append(f"Q{t[j]}_Q{t[j+1]}")


def init_qpu():
    init_db()
    name = "SAMPLE"
    date = "2024-12-05"
    installed_at = datetime.strptime(date, "%Y-%m-%d")
    # date = datetime.strptime(date, "%Y-%m-%d")
    qpu = QPUModel(
        name=name,
        nodes=new_nodes,
        edges=new_edges,
        size=64,
        active=True,
        installed_at=installed_at,
    )
    qpu.insert()


def delete_qpu():
    init_db()
    QPUModel.delete_all()


if __name__ == "__main__":
    init_db()
    init_qpu()
