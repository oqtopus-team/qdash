from qdash.common.config.loader import ConfigLoader
from qdash.common.config.topology import list_topologies, load_topology


def _write_topology(path, topology_id: str, num_qubits: int = 2) -> None:
    path.write_text(
        f"""
id: {topology_id}
name: Test Topology
grid_size: 2
num_qubits: {num_qubits}
qubits:
  0:
    row: 0
    col: 0
  1:
    row: 0
    col: 1
couplings:
  - [0, 1]
"""
    )


def test_load_topology_reads_domain_topologies(monkeypatch, tmp_path):
    topologies_dir = tmp_path / "domain" / "topologies"
    topologies_dir.mkdir(parents=True)
    _write_topology(topologies_dir / "test-topology.yaml", "test-topology")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    load_topology.cache_clear()

    topology = load_topology("test-topology")

    assert topology.id == "test-topology"
    assert topology.num_qubits == 2

    load_topology.cache_clear()


def test_list_topologies_reads_domain_topologies(monkeypatch, tmp_path):
    topologies_dir = tmp_path / "domain" / "topologies"
    topologies_dir.mkdir(parents=True)
    _write_topology(topologies_dir / "test-topology.yaml", "test-topology", num_qubits=4)
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)

    assert list_topologies(size=4) == [
        {"id": "test-topology", "name": "Test Topology", "num_qubits": 4}
    ]


def test_builtin_16q_square_lattice_mux_topology(monkeypatch):
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", ConfigLoader.LOCAL_CONFIG_DIR)
    load_topology.cache_clear()

    topology = load_topology("square-lattice-mux-16")

    assert topology.grid_size == 4
    assert topology.num_qubits == 16
    assert len(topology.qubits) == 16
    assert len(topology.couplings) == 24
    assert topology.mux.enabled is True
    assert topology.mux.size == 2

    load_topology.cache_clear()
