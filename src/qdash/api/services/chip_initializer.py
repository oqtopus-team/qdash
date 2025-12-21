"""Chip initialization service for API layer."""

import logging
from collections.abc import Mapping
from typing import Any

from qdash.api.lib.topology_config import load_topology
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.qubit import QubitDocument

logger = logging.getLogger(__name__)


class ChipInitializer:
    """Service class for initializing chips with proper data structures."""

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
        for qid in topology_qubits:
            qubit_doc = QubitDocument(
                project_id=project_id,
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
        for edge in edges:
            coupling_doc = CouplingDocument(
                project_id=project_id,
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
        # Set default topology_id if not provided
        if topology_id is None:
            topology_id = f"square-lattice-mux-{size}"

        # Load topology definition
        try:
            topology = load_topology(topology_id)
        except FileNotFoundError as e:
            msg = f"Topology '{topology_id}' not found"
            raise ValueError(msg) from e

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
