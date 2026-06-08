"""Chip initialization service for API layer."""

import logging
from collections.abc import Mapping
from typing import Any

from qdash.common.config.topology import TopologyDefinition, load_topology
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.user import UserDocument

logger = logging.getLogger(__name__)


class ChipInitializer:
    """Service class for initializing chips with proper data structures."""

    @staticmethod
    def _user_id_for_username(username: str) -> str | None:
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    @staticmethod
    def _bi_direction(edges: list[list[int]]) -> list[tuple[int, int]]:
        """Convert edges to bi-directional tuples.

        Args:
        ----
            edges: List of edge pairs [q1, q2]

        Returns:
        -------
            List of bi-directional edge tuples

        """
        result = []
        for edge in edges:
            result.append((edge[0], edge[1]))
            result.append((edge[1], edge[0]))
        return result

    @staticmethod
    def _load_topology(topology_id: str | None, size: int) -> tuple[str, TopologyDefinition]:
        if topology_id is None:
            topology_id = f"square-lattice-mux-{size}"
        try:
            return topology_id, load_topology(topology_id)
        except FileNotFoundError as e:
            msg = f"Topology '{topology_id}' not found"
            raise ValueError(msg) from e

    @staticmethod
    def _generate_qubit_documents(
        topology_qubits: Mapping[int, Any],
        username: str,
        chip_id: str,
        project_id: str | None = None,
    ) -> list[QubitDocument]:
        """Generate QubitDocument instances for database insertion.

        Args:
        ----
            topology_qubits: Qubit positions from topology definition
            username: Username
            chip_id: Chip ID
            project_id: Project ID

        Returns:
        -------
            List of QubitDocument instances

        """
        documents = []
        user_id = ChipInitializer._user_id_for_username(username)
        for qid in topology_qubits:
            qubit_doc = QubitDocument(
                project_id=project_id,
                user_id=user_id,
                username=username,
                chip_id=chip_id,
                qid=f"{qid}",
                status="pending",
                data={},
                system_info={},
            )
            documents.append(qubit_doc)
        return documents

    @staticmethod
    def _generate_coupling_documents(
        edges: list[tuple[int, int]],
        username: str,
        chip_id: str,
        project_id: str | None = None,
    ) -> list[CouplingDocument]:
        """Generate CouplingDocument instances for database insertion.

        Args:
        ----
            edges: List of bi-directional edge tuples
            username: Username
            chip_id: Chip ID
            project_id: Project ID

        Returns:
        -------
            List of CouplingDocument instances

        """
        documents = []
        user_id = ChipInitializer._user_id_for_username(username)
        for edge in edges:
            coupling_doc = CouplingDocument(
                project_id=project_id,
                user_id=user_id,
                username=username,
                qid=f"{edge[0]}-{edge[1]}",
                status="pending",
                chip_id=chip_id,
                data={},
                system_info={},
            )
            documents.append(coupling_doc)
        return documents

    @classmethod
    def create_chip(
        cls,
        username: str,
        chip_id: str,
        size: int,
        project_id: str | None = None,
        topology_id: str | None = None,
    ) -> ChipDocument:
        """Create a new chip with full initialization.

        This method creates:
        1. ChipDocument with qubit and coupling structure
        2. Individual QubitDocument entries
        3. Individual CouplingDocument entries

        Args:
        ----
            username: Username creating the chip
            chip_id: Unique chip identifier
            size: Chip size (number of qubits)
            project_id: Project ID for multi-tenancy
            topology_id: Topology template ID (required)

        Returns:
        -------
            The created ChipDocument

        Raises:
        ------
            ValueError: If topology not found or chip_id already exists
            FileNotFoundError: If topology file doesn't exist

        """
        # Load topology definition
        topology_id, topology = cls._load_topology(topology_id, size)

        # Validate size matches topology
        if size != topology.num_qubits:
            msg = f"Size {size} does not match topology num_qubits {topology.num_qubits}"
            raise ValueError(msg)

        # Check if chip already exists (scoped by project)
        query = {"chip_id": chip_id, "username": username}
        if project_id:
            query["project_id"] = project_id
        existing_chip = ChipDocument.find_one(query).run()
        if existing_chip:
            msg = f"Chip {chip_id} already exists for user {username}"
            raise ValueError(msg)

        try:
            # Get qubit positions and couplings from topology
            topology_qubits = topology.qubits
            bi_edges = cls._bi_direction(topology.couplings)

            # Create and save ChipDocument (without embedded qubits/couplings)
            chip = ChipDocument(
                project_id=project_id,
                user_id=cls._user_id_for_username(username),
                username=username,
                chip_id=chip_id,
                size=size,
                topology_id=topology_id,
                system_info={},
            )
            chip.save()

            # Generate and insert individual qubit documents
            qubit_documents = cls._generate_qubit_documents(
                topology_qubits, username, chip_id, project_id
            )
            for qubit_doc in qubit_documents:
                qubit_doc.insert()

            # Generate and insert individual coupling documents
            coupling_documents = cls._generate_coupling_documents(
                bi_edges, username, chip_id, project_id
            )
            for coupling_doc in coupling_documents:
                coupling_doc.insert()

            logger.info(
                f"Successfully created chip {chip_id} for user {username} "
                f"(project={project_id}) with topology {topology_id}"
            )
            return chip

        except Exception as e:
            logger.error(f"Error creating chip {chip_id}: {e}")
            raise

    @classmethod
    def ensure_topology_documents(
        cls,
        *,
        project_id: str,
        chip_id: str,
        topology_id: str | None,
        size: int,
    ) -> tuple[int, int]:
        """Create missing qubit/coupling skeleton rows for a chip topology.

        Existing rows are left untouched so calibration data and notes are preserved.
        """
        chip = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if chip is None:
            raise ValueError(f"Chip {chip_id} not found")

        topology_id, topology = cls._load_topology(topology_id, size)
        if size != topology.num_qubits:
            msg = f"Size {size} does not match topology num_qubits {topology.num_qubits}"
            raise ValueError(msg)

        existing_qubits = {
            doc.qid
            for doc in QubitDocument.find(
                QubitDocument.project_id == project_id,
                QubitDocument.chip_id == chip_id,
            ).run()
        }
        missing_qubits = [
            doc
            for doc in cls._generate_qubit_documents(
                topology.qubits,
                chip.username,
                chip_id,
                project_id,
            )
            if doc.qid not in existing_qubits
        ]
        for doc in missing_qubits:
            doc.insert()

        existing_couplings = {
            doc.qid
            for doc in CouplingDocument.find(
                CouplingDocument.project_id == project_id,
                CouplingDocument.chip_id == chip_id,
            ).run()
        }
        missing_couplings = [
            doc
            for doc in cls._generate_coupling_documents(
                cls._bi_direction(topology.couplings),
                chip.username,
                chip_id,
                project_id,
            )
            if doc.qid not in existing_couplings
        ]
        for doc in missing_couplings:
            doc.insert()

        if missing_qubits or missing_couplings:
            logger.info(
                "Created missing topology documents for chip %s: %d qubits, %d couplings",
                chip_id,
                len(missing_qubits),
                len(missing_couplings),
            )
        return len(missing_qubits), len(missing_couplings)

    @classmethod
    def ensure_qubit_document(cls, *, project_id: str, chip_id: str, qid: str) -> QubitDocument:
        """Return a qubit row, creating a topology-valid empty row when missing."""
        doc = QubitDocument.find_one(
            QubitDocument.project_id == project_id,
            QubitDocument.chip_id == chip_id,
            QubitDocument.qid == qid,
        ).run()
        if doc is not None:
            return doc

        chip = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if chip is None:
            raise ValueError(f"Chip {chip_id} not found")
        _, topology = cls._load_topology(chip.topology_id, chip.size)
        try:
            topology_qid = int(qid)
        except ValueError as e:
            raise ValueError(f"Qubit {qid} is not part of topology {chip.topology_id}") from e
        if topology_qid not in topology.qubits:
            raise ValueError(f"Qubit {qid} is not part of topology {chip.topology_id}")

        new_doc = cls._generate_qubit_documents(
            {topology_qid: topology.qubits[topology_qid]},
            chip.username,
            chip_id,
            project_id,
        )[0]
        new_doc.insert()
        return new_doc

    @classmethod
    def ensure_coupling_document(
        cls, *, project_id: str, chip_id: str, coupling_id: str
    ) -> CouplingDocument:
        """Return a coupling row, creating a topology-valid empty row when missing."""
        doc = CouplingDocument.find_one(
            CouplingDocument.project_id == project_id,
            CouplingDocument.chip_id == chip_id,
            CouplingDocument.qid == coupling_id,
        ).run()
        if doc is not None:
            return doc

        chip = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if chip is None:
            raise ValueError(f"Chip {chip_id} not found")
        _, topology = cls._load_topology(chip.topology_id, chip.size)
        try:
            a, b = (int(part) for part in coupling_id.split("-", 1))
        except ValueError as e:
            raise ValueError(
                f"Coupling {coupling_id} is not part of topology {chip.topology_id}"
            ) from e
        if (a, b) not in cls._bi_direction(topology.couplings):
            raise ValueError(f"Coupling {coupling_id} is not part of topology {chip.topology_id}")

        new_doc = cls._generate_coupling_documents(
            [(a, b)],
            chip.username,
            chip_id,
            project_id,
        )[0]
        new_doc.insert()
        return new_doc
