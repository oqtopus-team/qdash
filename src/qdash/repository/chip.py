"""MongoDB implementation of ChipRepository.

This module provides the concrete MongoDB implementation for chip
data persistence operations.
"""

import logging
from typing import Any

from qdash.datamodel.chip import ChipModel
from qdash.datamodel.task import CalibDataModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.coupling_history import CouplingHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.qubit_history import QubitHistoryDocument

logger = logging.getLogger(__name__)


class MongoChipRepository:
    """MongoDB implementation of ChipRepository.

    This class encapsulates all MongoDB-specific logic for chip data access,
    providing a clean abstraction over the underlying database operations.

    Example
    -------
        >>> repo = MongoChipRepository()
        >>> chips = repo.list_by_project(project_id="proj-1")
        >>> chip = repo.find_by_id(project_id="proj-1", chip_id="64Qv3")

    """

    def list_by_project(self, project_id: str) -> list[ChipModel]:
        """List all chips in a project.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        list[ChipModel]
            List of chips in the project

        """
        docs = ChipDocument.find({"project_id": project_id}).run()
        return [self._to_model(doc) for doc in docs]

    def find_by_id(self, project_id: str, chip_id: str) -> ChipModel | None:
        """Find a chip by project_id and chip_id.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        ChipModel | None
            The chip if found, None otherwise

        """
        doc = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
        if doc is None:
            return None
        return self._to_model(doc)

    def create(self, chip: ChipModel) -> ChipModel:
        """Create a new chip.

        Parameters
        ----------
        chip : ChipModel
            The chip to create

        Returns
        -------
        ChipModel
            The created chip

        Raises
        ------
        ValueError
            If a chip with the same chip_id already exists in the project

        """
        # Check for existing chip
        existing = ChipDocument.find_one(
            {"project_id": chip.project_id, "chip_id": chip.chip_id}
        ).run()
        if existing is not None:
            raise ValueError(f"Chip {chip.chip_id} already exists in project {chip.project_id}")

        # Create new document
        doc = ChipDocument(
            project_id=chip.project_id,
            chip_id=chip.chip_id,
            username=chip.username,
            size=chip.size,
            topology_id=chip.topology_id,
            installed_at=chip.installed_at,
            system_info=chip.system_info,
        )
        doc.insert()
        return self._to_model(doc)

    def find_one_document(self, query: dict[str, Any]) -> ChipDocument | None:
        """Find a single chip document by query.

        Parameters
        ----------
        query : dict[str, Any]
            MongoDB query dict

        Returns
        -------
        ChipDocument | None
            The chip document if found, None otherwise

        """
        return ChipDocument.find_one(query).run()

    def get_current_chip(self, username: str) -> ChipModel | None:
        """Get the most recently installed chip for a user.

        Parameters
        ----------
        username : str
            The username to look up the chip

        Returns
        -------
        ChipModel | None
            The current chip or None if not found

        """
        doc = self.find_one_document({"username": username})
        if doc is None:
            return None
        return self._to_model(doc)

    def get_chip_by_id(self, username: str, chip_id: str) -> ChipModel | None:
        """Get a specific chip by chip_id and username.

        Parameters
        ----------
        username : str
            The username of the chip owner
        chip_id : str
            The specific chip ID to retrieve

        Returns
        -------
        ChipModel | None
            The chip if found, None otherwise

        """
        doc = ChipDocument.find_one({"username": username, "chip_id": chip_id}).run()
        if doc is None:
            return None
        return self._to_model(doc)

    def update_chip_data(
        self,
        chip_id: str,
        calib_data: CalibDataModel,
        username: str,
    ) -> None:
        """Update chip calibration data.

        Parameters
        ----------
        chip_id : str
            The chip identifier
        calib_data : CalibDataModel
            The calibration data to merge
        username : str
            The user performing the update

        """
        ChipDocument.update_chip_data(
            chip_id=chip_id,
            calib_data=calib_data,
            username=username,
        )

    def _to_model(self, doc: ChipDocument) -> ChipModel:
        """Convert a document to a domain model.

        Parameters
        ----------
        doc : ChipDocument
            The MongoDB document

        Returns
        -------
        ChipModel
            The domain model

        """
        return ChipModel(
            project_id=doc.project_id,
            chip_id=doc.chip_id,
            username=doc.username,
            size=doc.size,
            topology_id=doc.topology_id,
            installed_at=doc.installed_at,
            system_info=doc.system_info,
        )

    # =========================================================================
    # Optimized methods for scalability (256+ qubits)
    # =========================================================================

    def list_summary_by_project(self, project_id: str) -> list[dict[str, Any]]:
        """List chips with summary info only (no qubit/coupling data).

        Uses MongoDB projection for efficient data transfer.
        Counts are fetched from individual QubitDocument/CouplingDocument collections.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        list[dict[str, Any]]
            List of chip summary dictionaries

        """
        docs = list(ChipDocument.find({"project_id": project_id}).run())
        return [
            {
                "chip_id": doc.chip_id,
                "size": doc.size,
                "topology_id": doc.topology_id,
                "installed_at": doc.installed_at,
                "qubit_count": self.get_qubit_count(project_id, doc.chip_id),
                "coupling_count": self.get_coupling_count(project_id, doc.chip_id),
            }
            for doc in docs
        ]

    def find_summary_by_id(self, project_id: str, chip_id: str) -> dict[str, Any] | None:
        """Find chip summary by ID (no qubit/coupling data).

        Counts are fetched from individual QubitDocument/CouplingDocument collections.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        dict[str, Any] | None
            Chip summary dictionary or None

        """
        doc = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
        if doc is None:
            return None
        return {
            "chip_id": doc.chip_id,
            "size": doc.size,
            "topology_id": doc.topology_id,
            "installed_at": doc.installed_at,
            "qubit_count": self.get_qubit_count(project_id, chip_id),
            "coupling_count": self.get_coupling_count(project_id, chip_id),
        }

    def list_qubits(
        self,
        project_id: str,
        chip_id: str,
        limit: int = 50,
        offset: int = 0,
        qids: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List qubits from QubitDocument collection with pagination.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        limit : int
            Maximum number of qubits
        offset : int
            Number to skip
        qids : list[str] | None
            Optional specific qubit IDs

        Returns
        -------
        tuple[list[dict[str, Any]], int]
            List of qubit dicts and total count

        """
        query: dict[str, Any] = {"project_id": project_id, "chip_id": chip_id}
        if qids:
            query["qid"] = {"$in": qids}

        total = QubitDocument.find(query).count()
        docs = list(QubitDocument.find(query).skip(offset).limit(limit).run())

        return (
            [
                {
                    "qid": doc.qid,
                    "chip_id": doc.chip_id,
                    "status": doc.status,
                    "data": doc.data,
                }
                for doc in docs
            ],
            total,
        )

    def find_qubit(self, project_id: str, chip_id: str, qid: str) -> dict[str, Any] | None:
        """Find a single qubit from QubitDocument collection.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        qid : str
            The qubit identifier

        Returns
        -------
        dict[str, Any] | None
            Qubit data or None

        """
        doc = QubitDocument.find_one(
            {"project_id": project_id, "chip_id": chip_id, "qid": qid}
        ).run()
        if doc is None:
            return None
        return {
            "qid": doc.qid,
            "chip_id": doc.chip_id,
            "status": doc.status,
            "data": doc.data,
        }

    def list_couplings(
        self,
        project_id: str,
        chip_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List couplings from CouplingDocument collection with pagination.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        limit : int
            Maximum number of couplings
        offset : int
            Number to skip

        Returns
        -------
        tuple[list[dict[str, Any]], int]
            List of coupling dicts and total count

        """
        query: dict[str, Any] = {"project_id": project_id, "chip_id": chip_id}

        total = CouplingDocument.find(query).count()
        docs = list(CouplingDocument.find(query).skip(offset).limit(limit).run())

        return (
            [
                {
                    "qid": doc.qid,
                    "chip_id": doc.chip_id,
                    "status": doc.status,
                    "data": doc.data,
                }
                for doc in docs
            ],
            total,
        )

    def find_coupling(
        self, project_id: str, chip_id: str, coupling_id: str
    ) -> dict[str, Any] | None:
        """Find a single coupling from CouplingDocument collection.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        coupling_id : str
            The coupling identifier

        Returns
        -------
        dict[str, Any] | None
            Coupling data or None

        """
        doc = CouplingDocument.find_one(
            {"project_id": project_id, "chip_id": chip_id, "qid": coupling_id}
        ).run()
        if doc is None:
            return None
        return {
            "qid": doc.qid,
            "chip_id": doc.chip_id,
            "status": doc.status,
            "data": doc.data,
        }

    def aggregate_metrics_summary(self, project_id: str, chip_id: str) -> dict[str, Any] | None:
        """Aggregate metrics summary using MongoDB pipeline.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        dict[str, Any] | None
            Aggregated metrics or None

        """
        # Check if chip exists first
        chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
        if chip is None:
            return None

        pipeline = [
            {"$match": {"project_id": project_id, "chip_id": chip_id}},
            {
                "$group": {
                    "_id": None,
                    "qubit_count": {"$sum": 1},
                    "calibrated_count": {
                        "$sum": {"$cond": [{"$ifNull": ["$data.t1.value", False]}, 1, 0]}
                    },
                    "avg_t1": {"$avg": "$data.t1.value"},
                    "avg_t2_echo": {"$avg": "$data.t2_echo.value"},
                    "avg_t2_star": {"$avg": "$data.t2_star.value"},
                    "avg_qubit_frequency": {"$avg": "$data.qubit_frequency.value"},
                    "avg_readout_fidelity": {"$avg": "$data.average_readout_fidelity.value"},
                }
            },
        ]

        results = list(QubitDocument.aggregate(pipeline).run())
        if not results:
            return {
                "qubit_count": 0,
                "calibrated_count": 0,
            }
        return dict(results[0])

    def aggregate_metric_heatmap(
        self,
        project_id: str,
        chip_id: str,
        metric: str,
        is_coupling: bool = False,
    ) -> dict[str, Any] | None:
        """Aggregate heatmap data for a single metric.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        metric : str
            The metric name
        is_coupling : bool
            Whether to query coupling or qubit collection

        Returns
        -------
        dict[str, Any] | None
            Heatmap data with values and unit

        """
        # Check if chip exists first
        chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
        if chip is None:
            return None

        collection = CouplingDocument if is_coupling else QubitDocument

        pipeline = [
            {"$match": {"project_id": project_id, "chip_id": chip_id}},
            {
                "$project": {
                    "qid": 1,
                    "value": f"$data.{metric}.value",
                    "unit": f"$data.{metric}.unit",
                }
            },
        ]

        results = list(collection.aggregate(pipeline).run())

        values: dict[str, float | None] = {}
        unit: str | None = None

        for r in results:
            qid = r.get("qid")
            if qid:
                values[qid] = r.get("value")
                if unit is None and r.get("unit"):
                    unit = r.get("unit")

        return {"values": values, "unit": unit}

    def get_qubit_ids(self, project_id: str, chip_id: str) -> list[str]:
        """Get all qubit IDs for a chip from QubitDocument collection.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        list[str]
            List of qubit IDs

        """
        pipeline = [
            {"$match": {"project_id": project_id, "chip_id": chip_id}},
            {"$project": {"qid": 1}},
        ]
        results = list(QubitDocument.aggregate(pipeline).run())
        return [r["qid"] for r in results if r.get("qid")]

    def get_qubit_fidelity_map(
        self, project_id: str, chip_id: str, threshold: float = 0.99
    ) -> dict[str, bool]:
        """Get fidelity threshold map for qubits.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        threshold : float
            Fidelity threshold (default 0.99)

        Returns
        -------
        dict[str, bool]
            Map of qubit ID to whether fidelity exceeds threshold

        """
        pipeline = [
            {"$match": {"project_id": project_id, "chip_id": chip_id}},
            {
                "$project": {
                    "qid": 1,
                    "fidelity": "$data.x90_gate_fidelity.value",
                }
            },
        ]
        results = list(QubitDocument.aggregate(pipeline).run())
        return {r["qid"]: (r.get("fidelity") or 0.0) > threshold for r in results if r.get("qid")}

    def get_coupling_ids(self, project_id: str, chip_id: str) -> list[str]:
        """Get all coupling IDs for a chip from CouplingDocument collection.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        list[str]
            List of coupling IDs

        """
        pipeline = [
            {"$match": {"project_id": project_id, "chip_id": chip_id}},
            {"$project": {"qid": 1}},
        ]
        results = list(CouplingDocument.aggregate(pipeline).run())
        return [r["qid"] for r in results if r.get("qid")]

    def get_coupling_fidelity_map(
        self,
        project_id: str,
        chip_id: str,
        threshold: float = 0.75,
        metric: str = "bell_state_fidelity",
    ) -> dict[str, bool]:
        """Get fidelity threshold map for couplings.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        threshold : float
            Fidelity threshold (default 0.75)
        metric : str
            The fidelity metric to check (default "bell_state_fidelity")

        Returns
        -------
        dict[str, bool]
            Map of coupling ID to whether fidelity exceeds threshold

        """
        pipeline = [
            {"$match": {"project_id": project_id, "chip_id": chip_id}},
            {
                "$project": {
                    "qid": 1,
                    "fidelity": f"$data.{metric}.value",
                }
            },
        ]
        results = list(CouplingDocument.aggregate(pipeline).run())
        return {r["qid"]: (r.get("fidelity") or 0.0) > threshold for r in results if r.get("qid")}

    def get_qubits_by_ids(
        self, project_id: str, chip_id: str, qids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Get multiple qubits by their IDs.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        qids : list[str]
            List of qubit IDs to fetch

        Returns
        -------
        dict[str, dict[str, Any]]
            Map of qubit ID to qubit data

        """
        docs = list(
            QubitDocument.find(
                {"project_id": project_id, "chip_id": chip_id, "qid": {"$in": qids}}
            ).run()
        )
        return {
            doc.qid: {
                "qid": doc.qid,
                "chip_id": doc.chip_id,
                "status": doc.status,
                "data": doc.data,
            }
            for doc in docs
        }

    def get_couplings_by_ids(
        self, project_id: str, chip_id: str, coupling_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Get multiple couplings by their IDs.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        coupling_ids : list[str]
            List of coupling IDs to fetch

        Returns
        -------
        dict[str, dict[str, Any]]
            Map of coupling ID to coupling data

        """
        docs = list(
            CouplingDocument.find(
                {"project_id": project_id, "chip_id": chip_id, "qid": {"$in": coupling_ids}}
            ).run()
        )
        return {
            doc.qid: {
                "qid": doc.qid,
                "chip_id": doc.chip_id,
                "status": doc.status,
                "data": doc.data,
            }
            for doc in docs
        }

    # Entity model methods for metrics extraction

    def get_all_qubit_models(self, project_id: str, chip_id: str) -> dict[str, QubitDocument]:
        """Get all qubit documents as a dict keyed by qubit ID.

        Returns documents that can be used directly with _extract_latest_metrics
        since QubitDocument has a .data attribute.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        dict[str, QubitDocument]
            Map of qubit ID to QubitDocument

        """
        docs = list(QubitDocument.find({"project_id": project_id, "chip_id": chip_id}).run())
        return {doc.qid: doc for doc in docs}

    def get_all_coupling_models(self, project_id: str, chip_id: str) -> dict[str, CouplingDocument]:
        """Get all coupling documents as a dict keyed by coupling ID.

        Returns documents that can be used directly with _extract_latest_metrics
        since CouplingDocument has a .data attribute.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        dict[str, CouplingDocument]
            Map of coupling ID to CouplingDocument

        """
        docs = list(CouplingDocument.find({"project_id": project_id, "chip_id": chip_id}).run())
        return {doc.qid: doc for doc in docs}

    def get_qubit_count(self, project_id: str, chip_id: str) -> int:
        """Get the number of qubits for a chip.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        int
            Number of qubits

        """
        count: int = QubitDocument.find({"project_id": project_id, "chip_id": chip_id}).count()
        return count

    def get_coupling_count(self, project_id: str, chip_id: str) -> int:
        """Get the number of couplings for a chip.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        int
            Number of couplings

        """
        count: int = CouplingDocument.find({"project_id": project_id, "chip_id": chip_id}).count()
        return count

    # Historical data methods (using QubitHistoryDocument/CouplingHistoryDocument)

    def get_historical_qubit_ids(
        self, project_id: str, chip_id: str, recorded_date: str
    ) -> list[str]:
        """Get all qubit IDs for a chip at a specific historical date.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        recorded_date : str
            The date in YYYYMMDD format

        Returns
        -------
        list[str]
            List of qubit IDs

        """
        pipeline = [
            {
                "$match": {
                    "project_id": project_id,
                    "chip_id": chip_id,
                    "recorded_date": recorded_date,
                }
            },
            {"$project": {"qid": 1}},
        ]
        results = list(QubitHistoryDocument.aggregate(pipeline).run())
        return [r["qid"] for r in results if r.get("qid")]

    def get_historical_qubit_fidelity_map(
        self,
        project_id: str,
        chip_id: str,
        recorded_date: str,
        threshold: float = 0.99,
    ) -> dict[str, dict[str, Any]]:
        """Get fidelity data for qubits at a specific historical date.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        recorded_date : str
            The date in YYYYMMDD format
        threshold : float
            Fidelity threshold (default 0.99)

        Returns
        -------
        dict[str, dict[str, Any]]
            Map of qubit ID to fidelity info (value, calibrated_at, over_threshold)

        """
        docs = list(
            QubitHistoryDocument.find(
                {
                    "project_id": project_id,
                    "chip_id": chip_id,
                    "recorded_date": recorded_date,
                }
            ).run()
        )
        result = {}
        for doc in docs:
            fidelity_data = doc.data.get("x90_gate_fidelity", {})
            value = fidelity_data.get("value", 0.0)
            calibrated_at = fidelity_data.get("calibrated_at")
            result[doc.qid] = {
                "value": value,
                "calibrated_at": calibrated_at,
                "over_threshold": value > threshold,
            }
        return result

    def get_historical_coupling_ids(
        self, project_id: str, chip_id: str, recorded_date: str
    ) -> list[str]:
        """Get all coupling IDs for a chip at a specific historical date.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        recorded_date : str
            The date in YYYYMMDD format

        Returns
        -------
        list[str]
            List of coupling IDs

        """
        pipeline = [
            {
                "$match": {
                    "project_id": project_id,
                    "chip_id": chip_id,
                    "recorded_date": recorded_date,
                }
            },
            {"$project": {"qid": 1}},
        ]
        results = list(CouplingHistoryDocument.aggregate(pipeline).run())
        return [r["qid"] for r in results if r.get("qid")]

    def get_historical_coupling_fidelity_map(
        self,
        project_id: str,
        chip_id: str,
        recorded_date: str,
        threshold: float = 0.75,
        metric: str = "bell_state_fidelity",
    ) -> dict[str, dict[str, Any]]:
        """Get fidelity data for couplings at a specific historical date.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        recorded_date : str
            The date in YYYYMMDD format
        threshold : float
            Fidelity threshold (default 0.75)
        metric : str
            The fidelity metric to check (default "bell_state_fidelity")

        Returns
        -------
        dict[str, dict[str, Any]]
            Map of coupling ID to fidelity info (value, calibrated_at, over_threshold)

        """
        docs = list(
            CouplingHistoryDocument.find(
                {
                    "project_id": project_id,
                    "chip_id": chip_id,
                    "recorded_date": recorded_date,
                }
            ).run()
        )
        result = {}
        for doc in docs:
            fidelity_data = doc.data.get(metric, {})
            value = fidelity_data.get("value", 0.0)
            calibrated_at = fidelity_data.get("calibrated_at")
            result[doc.qid] = {
                "value": value,
                "calibrated_at": calibrated_at,
                "over_threshold": value > threshold,
            }
        return result
