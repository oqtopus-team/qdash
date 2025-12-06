"""Chip initialization service for API layer."""

import logging
from typing import Dict, List, Tuple

from qdash.datamodel.coupling import CouplingModel, EdgeInfoModel
from qdash.datamodel.qubit import NodeInfoModel, PositionModel, QubitModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.qubit import QubitDocument

logger = logging.getLogger(__name__)


class ChipInitializer:
    """Service class for initializing chips with proper data structures."""

    VALID_SIZES = [64, 144, 256, 1024]
    SIZE_TO_DIMENSION = {
        64: 4,
        144: 6,
        256: 8,
        1024: 16,
    }

    @staticmethod
    def _qubit_lattice(n: int, d: int) -> Tuple[range, List[Tuple[int, int]], Dict[int, Tuple[float, float]]]:
        """Generate qubit lattice structure for RQC square lattice.

        Args:
        ----
            n (int): Number of qubits
            d (int): Dimension of the lattice

        Returns:
        -------
            Tuple containing nodes range, edges list, and position dictionary

        """

        def node(i: int, j: int, k: int) -> int:
            return 4 * (i * d + j) + k

        nodes = range(n)
        edges = []
        for i in range(d):
            for j in range(d):
                # inner - mux
                edges.append((node(i, j, 0), node(i, j, 1)))
                edges.append((node(i, j, 0), node(i, j, 2)))
                edges.append((node(i, j, 1), node(i, j, 3)))
                edges.append((node(i, j, 2), node(i, j, 3)))

                # inter - mux
                if i != d - 1:
                    edges.append((node(i, j, 2), node(i + 1, j, 0)))
                    edges.append((node(i, j, 3), node(i + 1, j, 1)))
                if j != d - 1:
                    edges.append((node(i, j, 1), node(i, j + 1, 0)))
                    edges.append((node(i, j, 3), node(i, j + 1, 2)))

        # Uniform grid layout
        pos = {}
        scale = 50  # spacing between nodes
        for i in range(d):
            for j in range(d):
                x_base = j * 2 * scale
                y_base = -i * 2 * scale
                pos[node(i, j, 0)] = (x_base, y_base)
                pos[node(i, j, 1)] = (x_base + scale, y_base)
                pos[node(i, j, 2)] = (x_base, y_base - scale)
                pos[node(i, j, 3)] = (x_base + scale, y_base - scale)

        return nodes, edges, pos

    @staticmethod
    def _bi_direction(edges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Convert edges to bi-directional.

        Args:
        ----
            edges: List of edge tuples

        Returns:
        -------
            List of bi-directional edges

        """
        return edges + [(j, i) for i, j in edges]

    @staticmethod
    def _generate_qubit_data(
        num_qubits: int,
        pos: Dict[int, Tuple[float, float]],
        chip_id: str,
        username: str,
        project_id: str | None = None,
    ) -> Dict[str, QubitModel]:
        """Generate qubit data for ChipDocument.

        Args:
        ----
            num_qubits: Number of qubits
            pos: Position dictionary
            chip_id: Chip ID
            username: Username
            project_id: Project ID

        Returns:
        -------
            Dictionary of qubit models

        """
        qubits = {}
        for i in range(num_qubits):
            qubits[f"{i}"] = QubitModel(
                project_id=project_id,
                username=username,
                chip_id=chip_id,
                qid=f"{i}",
                status="pending",
                node_info=NodeInfoModel(
                    position=PositionModel(
                        x=pos[i][0],
                        y=pos[i][1],
                    ),
                ),
                data={},
                best_data={},
            )
        return qubits

    @staticmethod
    def _generate_coupling_data(
        edges: List[Tuple[int, int]],
        chip_id: str,
        username: str,
        project_id: str | None = None,
    ) -> Dict[str, CouplingModel]:
        """Generate coupling data for ChipDocument.

        Args:
        ----
            edges: List of edge tuples
            chip_id: Chip ID
            username: Username
            project_id: Project ID

        Returns:
        -------
            Dictionary of coupling models

        """
        bi_edges = ChipInitializer._bi_direction(edges)
        couplings = {}
        for edge in bi_edges:
            couplings[f"{edge[0]}-{edge[1]}"] = CouplingModel(
                project_id=project_id,
                username=username,
                qid=f"{edge[0]}-{edge[1]}",
                status="pending",
                chip_id=chip_id,
                data={},
                best_data={},
                edge_info=EdgeInfoModel(size=4, fill="", source=f"{edge[0]}", target=f"{edge[1]}"),
            )
        return couplings

    @staticmethod
    def _generate_qubit_documents(
        num_qubits: int,
        pos: Dict[int, Tuple[float, float]],
        username: str,
        chip_id: str,
        project_id: str | None = None,
    ) -> List[QubitDocument]:
        """Generate QubitDocument instances for database insertion.

        Args:
        ----
            num_qubits: Number of qubits
            pos: Position dictionary
            username: Username
            chip_id: Chip ID
            project_id: Project ID

        Returns:
        -------
            List of QubitDocument instances

        """
        documents = []
        for i in range(num_qubits):
            qubit_doc = QubitDocument(
                project_id=project_id,
                username=username,
                chip_id=chip_id,
                qid=f"{i}",
                status="pending",
                node_info=NodeInfoModel(
                    position=PositionModel(
                        x=pos[i][0],
                        y=pos[i][1],
                    ),
                ),
                data={},
                best_data={},
                system_info={},
            )
            documents.append(qubit_doc)
        return documents

    @staticmethod
    def _generate_coupling_documents(
        edges: List[Tuple[int, int]],
        username: str,
        chip_id: str,
        project_id: str | None = None,
    ) -> List[CouplingDocument]:
        """Generate CouplingDocument instances for database insertion.

        Args:
        ----
            edges: List of edge tuples
            username: Username
            chip_id: Chip ID
            project_id: Project ID

        Returns:
        -------
            List of CouplingDocument instances

        """
        bi_edges = ChipInitializer._bi_direction(edges)
        documents = []
        for edge in bi_edges:
            coupling_doc = CouplingDocument(
                project_id=project_id,
                username=username,
                qid=f"{edge[0]}-{edge[1]}",
                status="pending",
                chip_id=chip_id,
                data={},
                best_data={},
                edge_info=EdgeInfoModel(size=4, fill="", source=f"{edge[0]}", target=f"{edge[1]}"),
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
            size: Chip size (must be in VALID_SIZES)
            project_id: Project ID for multi-tenancy

        Returns:
        -------
            The created ChipDocument

        Raises:
        ------
            ValueError: If size is invalid or chip_id already exists

        """
        # Validate size
        if size not in cls.VALID_SIZES:
            msg = f"Invalid chip size. Must be one of {cls.VALID_SIZES}"
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
            # Get dimension
            d = cls.SIZE_TO_DIMENSION[size]

            # Generate lattice structure
            _, edges, pos = cls._qubit_lattice(size, d)

            # Generate qubit and coupling data for ChipDocument
            qubits = cls._generate_qubit_data(size, pos, chip_id, username, project_id)
            couplings = cls._generate_coupling_data(edges, chip_id, username, project_id)

            # Create and save ChipDocument
            chip = ChipDocument(
                project_id=project_id,
                username=username,
                chip_id=chip_id,
                size=size,
                qubits=qubits,
                couplings=couplings,
                system_info={},
            )
            chip.save()

            # Generate and insert individual qubit documents
            qubit_documents = cls._generate_qubit_documents(size, pos, username, chip_id, project_id)
            for qubit_doc in qubit_documents:
                qubit_doc.insert()

            # Generate and insert individual coupling documents
            coupling_documents = cls._generate_coupling_documents(edges, username, chip_id, project_id)
            for coupling_doc in coupling_documents:
                coupling_doc.insert()

            logger.info(f"Successfully created chip {chip_id} for user {username} (project={project_id}) with size {size}")
            return chip

        except Exception as e:
            logger.error(f"Error creating chip {chip_id}: {e}")
            raise
