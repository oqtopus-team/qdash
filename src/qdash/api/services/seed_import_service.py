"""Seed import service for importing initial calibration parameters.

This module provides functionality to import seed parameters from qubex
params directory or manual input into QDash's calibration database,
with full provenance tracking.
"""

from __future__ import annotations

import logging
import pathlib
import re
import uuid
from typing import Any

import yaml
from qdash.api.schemas.calibration import (
    SeedImportRequest,
    SeedImportResponse,
    SeedImportResultItem,
    SeedImportSource,
)
from qdash.common.datetime_utils import now
from qdash.common.paths import QUBEX_CONFIG_BASE
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.provenance import ProvenanceRelationType
from qdash.dbmodel.qubit import QubitDocument
from qdash.repository.provenance import (
    MongoActivityRepository,
    MongoParameterVersionRepository,
    MongoProvenanceRelationRepository,
)

logger = logging.getLogger(__name__)

# Default seed parameters that are commonly imported
DEFAULT_SEED_PARAMETERS = [
    "qubit_frequency",
    "readout_amplitude",
    "readout_frequency",
    "control_amplitude",
]


class SeedImportService:
    """Service for importing seed calibration parameters.

    This service handles importing initial calibration parameters from
    qubex's params directory or from manual input into QDash's MongoDB,
    with full provenance tracking for data lineage.
    """

    def __init__(self) -> None:
        """Initialize the seed import service."""
        self._config_base = QUBEX_CONFIG_BASE
        self._activity_repo = MongoActivityRepository()
        self._param_version_repo = MongoParameterVersionRepository()
        self._relation_repo = MongoProvenanceRelationRepository()

    def _params_dir(self, chip_id: str) -> pathlib.Path:
        """Get the params directory for a chip.

        Parameters
        ----------
        chip_id : str
            Chip identifier (must contain only alphanumeric, underscore, or hyphen)

        Returns
        -------
        pathlib.Path
            Path to the params directory

        Raises
        ------
        ValueError
            If chip_id contains invalid characters (path traversal prevention)

        """
        # Validate chip_id to prevent path traversal attacks
        if not re.match(r"^[a-zA-Z0-9_-]+$", chip_id):
            raise ValueError(f"Invalid chip_id: {chip_id}")
        return pathlib.Path(self._config_base) / chip_id / "params"

    def import_seeds(
        self,
        request: SeedImportRequest,
        project_id: str,
        username: str,
    ) -> SeedImportResponse:
        """Import seed parameters from the specified source.

        Parameters
        ----------
        request : SeedImportRequest
            Import request with source and parameters
        project_id : str
            Target project ID
        username : str
            Username performing the import

        Returns
        -------
        SeedImportResponse
            Results of the import operation

        """
        if request.source == SeedImportSource.QUBEX_PARAMS:
            return self._import_from_qubex(request, project_id, username)
        elif request.source == SeedImportSource.MANUAL:
            return self._import_from_manual(request, project_id, username)
        else:
            raise ValueError(f"Unknown source: {request.source}")

    def _import_from_qubex(
        self,
        request: SeedImportRequest,
        project_id: str,
        username: str,
    ) -> SeedImportResponse:
        """Import parameters from qubex params directory.

        Parameters
        ----------
        request : SeedImportRequest
            Import request
        project_id : str
            Target project ID
        username : str
            Username performing the import

        Returns
        -------
        SeedImportResponse
            Results of the import operation

        """
        params_dir = self._params_dir(request.chip_id)
        parameters = request.parameters or DEFAULT_SEED_PARAMETERS
        results: list[SeedImportResultItem] = []
        imported_count = 0
        skipped_count = 0
        error_count = 0

        # Create execution and task IDs for provenance
        execution_id = f"seed-import-{uuid.uuid4().hex[:8]}"
        task_id = f"seed-import-qubex-{uuid.uuid4().hex[:8]}"
        start_time = now()

        # Create activity for provenance tracking
        activity = self._activity_repo.create_activity(
            execution_id=execution_id,
            task_id=task_id,
            task_name="SeedImport",
            project_id=project_id,
            task_type="seed_import",
            qid="",  # Multi-qubit operation
            chip_id=request.chip_id,
            started_at=start_time,
            status="running",
        )

        for param_name in parameters:
            yaml_path = params_dir / f"{param_name}.yaml"

            if not yaml_path.exists():
                logger.warning(f"Parameter file not found: {yaml_path}")
                skipped_count += 1
                continue

            try:
                param_data = self._load_param_yaml(yaml_path)
                meta = param_data.get("meta", {})
                data = param_data.get("data", {})
                unit = meta.get("unit", "")

                for qid, value in data.items():
                    # Filter by qids if specified
                    if request.qids and qid not in request.qids:
                        continue

                    # Skip null values
                    if value is None:
                        skipped_count += 1
                        continue

                    try:
                        # Upsert to QubitDocument
                        self._upsert_qubit_parameter(
                            project_id=project_id,
                            username=username,
                            chip_id=request.chip_id,
                            qid=qid,
                            param_name=param_name,
                            value=value,
                            unit=unit,
                        )

                        # Record provenance
                        self._record_provenance(
                            project_id=project_id,
                            chip_id=request.chip_id,
                            param_name=param_name,
                            qid=qid,
                            value=value,
                            unit=unit,
                            execution_id=execution_id,
                            task_id=task_id,
                            activity_id=activity.activity_id,
                        )

                        results.append(
                            SeedImportResultItem(
                                parameter_name=param_name,
                                qid=qid,
                                value=value,
                                unit=unit,
                                status="imported",
                            )
                        )
                        imported_count += 1
                    except Exception as e:
                        logger.error(f"Failed to import {param_name} for {qid}: {e}")
                        results.append(
                            SeedImportResultItem(
                                parameter_name=param_name,
                                qid=qid,
                                value=value,
                                unit=unit,
                                status="error",
                                message=str(e),
                            )
                        )
                        error_count += 1

            except Exception as e:
                logger.error(f"Failed to load {yaml_path}: {e}")
                error_count += 1

        # Update activity status
        activity.ended_at = now()
        activity.status = "completed" if error_count == 0 else "completed_with_errors"
        activity.save()

        return SeedImportResponse(
            chip_id=request.chip_id,
            source=request.source.value,
            imported_count=imported_count,
            skipped_count=skipped_count,
            error_count=error_count,
            results=results,
            provenance_activity_id=activity.activity_id,
        )

    def _import_from_manual(
        self,
        request: SeedImportRequest,
        project_id: str,
        username: str,
    ) -> SeedImportResponse:
        """Import parameters from manual input.

        Parameters
        ----------
        request : SeedImportRequest
            Import request with manual_data
        project_id : str
            Target project ID
        username : str
            Username performing the import

        Returns
        -------
        SeedImportResponse
            Results of the import operation

        """
        if not request.manual_data:
            raise ValueError("manual_data is required for MANUAL source")

        results: list[SeedImportResultItem] = []
        imported_count = 0
        skipped_count = 0
        error_count = 0

        # Create execution and task IDs for provenance
        execution_id = f"seed-import-{uuid.uuid4().hex[:8]}"
        task_id = f"seed-import-manual-{uuid.uuid4().hex[:8]}"
        start_time = now()

        # Create activity for provenance tracking
        activity = self._activity_repo.create_activity(
            execution_id=execution_id,
            task_id=task_id,
            task_name="SeedImportManual",
            project_id=project_id,
            task_type="seed_import",
            qid="",  # Multi-qubit operation
            chip_id=request.chip_id,
            started_at=start_time,
            status="running",
        )

        for param_name, qid_values in request.manual_data.items():
            for qid, value_data in qid_values.items():
                # Filter by qids if specified
                if request.qids and qid not in request.qids:
                    continue

                # Handle both simple values and dict with value/unit
                if isinstance(value_data, dict):
                    value = value_data.get("value", value_data)
                    unit = value_data.get("unit", "")
                else:
                    value = value_data
                    unit = ""

                # Skip null values
                if value is None:
                    skipped_count += 1
                    continue

                try:
                    # Upsert to QubitDocument
                    self._upsert_qubit_parameter(
                        project_id=project_id,
                        username=username,
                        chip_id=request.chip_id,
                        qid=qid,
                        param_name=param_name,
                        value=value,
                        unit=unit,
                    )

                    # Record provenance
                    self._record_provenance(
                        project_id=project_id,
                        chip_id=request.chip_id,
                        param_name=param_name,
                        qid=qid,
                        value=value,
                        unit=unit,
                        execution_id=execution_id,
                        task_id=task_id,
                        activity_id=activity.activity_id,
                    )

                    results.append(
                        SeedImportResultItem(
                            parameter_name=param_name,
                            qid=qid,
                            value=value,
                            unit=unit,
                            status="imported",
                        )
                    )
                    imported_count += 1
                except Exception as e:
                    logger.error(f"Failed to import {param_name} for {qid}: {e}")
                    results.append(
                        SeedImportResultItem(
                            parameter_name=param_name,
                            qid=qid,
                            value=value,
                            unit=unit,
                            status="error",
                            message=str(e),
                        )
                    )
                    error_count += 1

        # Update activity status
        activity.ended_at = now()
        activity.status = "completed" if error_count == 0 else "completed_with_errors"
        activity.save()

        return SeedImportResponse(
            chip_id=request.chip_id,
            source=request.source.value,
            imported_count=imported_count,
            skipped_count=skipped_count,
            error_count=error_count,
            results=results,
            provenance_activity_id=activity.activity_id,
        )

    def _load_param_yaml(self, path: pathlib.Path) -> dict[str, Any]:
        """Load a parameter YAML file.

        Parameters
        ----------
        path : Path
            Path to the YAML file

        Returns
        -------
        dict
            Parsed YAML content with 'meta' and 'data' keys

        """
        with open(path) as f:
            result: dict[str, Any] = yaml.safe_load(f)
            return result

    def _upsert_qubit_parameter(
        self,
        project_id: str,
        username: str,
        chip_id: str,
        qid: str,
        param_name: str,
        value: Any,
        unit: str,
    ) -> None:
        """Upsert a qubit parameter in the database.

        Creates the QubitDocument if it doesn't exist, otherwise updates it.

        Parameters
        ----------
        project_id : str
            Project ID
        username : str
            Username
        chip_id : str
            Chip ID
        qid : str
            Qubit ID (e.g., "Q00")
        param_name : str
            Parameter name (e.g., "qubit_frequency")
        value : Any
            Parameter value
        unit : str
            Parameter unit

        """
        # Normalize qid (remove 'Q' prefix for storage if present)
        normalized_qid = qid.lstrip("Q") if qid.startswith("Q") else qid

        # Find existing document
        qubit_doc = QubitDocument.find_one(
            {
                "project_id": project_id,
                "username": username,
                "chip_id": chip_id,
                "qid": normalized_qid,
            }
        ).run()

        param_data = {
            param_name: {
                "value": value,
                "unit": unit,
                "description": f"Imported from seed ({param_name})",
            }
        }

        if qubit_doc is None:
            # Create new document
            qubit_doc = QubitDocument(
                project_id=project_id,
                username=username,
                chip_id=chip_id,
                qid=normalized_qid,
                status="active",
                data=param_data,
                system_info=SystemInfoModel(),
            )
            qubit_doc.insert()
            logger.info(f"Created new QubitDocument for {chip_id}/{normalized_qid}")
        else:
            # Update existing document
            qubit_doc.data = QubitDocument.merge_calib_data(qubit_doc.data, param_data)
            qubit_doc.system_info.update_time()
            qubit_doc.save()
            logger.info(f"Updated QubitDocument for {chip_id}/{normalized_qid}")

    def _record_provenance(
        self,
        project_id: str,
        chip_id: str,
        param_name: str,
        qid: str,
        value: Any,
        unit: str,
        execution_id: str,
        task_id: str,
        activity_id: str,
    ) -> None:
        """Record provenance for an imported parameter.

        Creates a ParameterVersion and links it to the import activity
        via a wasGeneratedBy relation.

        Parameters
        ----------
        project_id : str
            Project ID
        chip_id : str
            Chip ID
        param_name : str
            Parameter name
        qid : str
            Qubit ID
        value : Any
            Parameter value
        unit : str
            Parameter unit
        execution_id : str
            Execution ID for this import
        task_id : str
            Task ID for this import
        activity_id : str
            Activity ID for provenance relation

        """
        # Determine value type
        if isinstance(value, float):
            value_type = "float"
        elif isinstance(value, int):
            value_type = "int"
        else:
            value_type = "str"
            value = str(value)

        # Create parameter version
        param_version = self._param_version_repo.create_version(
            parameter_name=param_name,
            qid=qid,
            value=value,
            execution_id=execution_id,
            task_id=task_id,
            project_id=project_id,
            task_name="SeedImport",
            chip_id=chip_id,
            unit=unit,
            error=0.0,
            value_type=value_type,
        )

        # Create wasGeneratedBy relation (entity -> activity)
        self._relation_repo.create_relation(
            relation_type=ProvenanceRelationType.GENERATED_BY,
            source_type="entity",
            source_id=param_version.entity_id,
            target_type="activity",
            target_id=activity_id,
            project_id=project_id,
            execution_id=execution_id,
        )

        logger.debug(
            f"Recorded provenance for {param_name}:{qid} " f"(entity_id={param_version.entity_id})"
        )

    def get_available_parameters(self, chip_id: str) -> list[str]:
        """Get list of available parameter files for a chip.

        Parameters
        ----------
        chip_id : str
            Chip ID

        Returns
        -------
        list[str]
            List of available parameter names

        """
        params_dir = self._params_dir(chip_id)
        if not params_dir.exists():
            return []

        return [
            p.stem
            for p in params_dir.glob("*.yaml")
            if not p.name.endswith(".lock") and p.stem not in ("params", "props")
        ]

    def compare_seed_values(
        self,
        chip_id: str,
        project_id: str,
        username: str,
        parameters: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compare YAML seed values with current QDash values.

        Parameters
        ----------
        chip_id : str
            Chip ID
        project_id : str
            Project ID
        username : str
            Username
        parameters : list[str] | None
            List of parameters to compare (None = all available)

        Returns
        -------
        dict
            Comparison data with structure:
            {
                "chip_id": str,
                "parameters": {
                    "param_name": {
                        "unit": str,
                        "qubits": {
                            "Q0": {
                                "yaml_value": float | None,
                                "qdash_value": float | None,
                                "status": "new" | "same" | "different" | "missing"
                            }
                        }
                    }
                }
            }

        """
        params_dir = self._params_dir(chip_id)
        available_params = self.get_available_parameters(chip_id)

        # Filter parameters if specified
        if parameters:
            param_list = [p for p in parameters if p in available_params]
        else:
            param_list = available_params

        # Get all qubit documents for this chip
        qubit_docs = list(
            QubitDocument.find(
                {
                    "project_id": project_id,
                    "username": username,
                    "chip_id": chip_id,
                }
            ).run()
        )

        # Build QDash values lookup: {qid: {param_name: value}}
        qdash_values: dict[str, dict[str, Any]] = {}
        for doc in qubit_docs:
            qid = f"Q{doc.qid}" if not doc.qid.startswith("Q") else doc.qid
            qdash_values[qid] = {}
            if doc.data:
                for param_name, param_data in doc.data.items():
                    if isinstance(param_data, dict) and "value" in param_data:
                        qdash_values[qid][param_name] = param_data["value"]

        # Build comparison data
        result: dict[str, Any] = {
            "chip_id": chip_id,
            "parameters": {},
        }

        for param_name in param_list:
            yaml_path = params_dir / f"{param_name}.yaml"
            if not yaml_path.exists():
                continue

            try:
                param_data = self._load_param_yaml(yaml_path)
                meta = param_data.get("meta", {})
                data = param_data.get("data", {})
                unit = meta.get("unit", "")

                param_comparison: dict[str, Any] = {
                    "unit": unit,
                    "qubits": {},
                }

                for qid, yaml_value in data.items():
                    if yaml_value is None:
                        continue

                    # Normalize qid for lookup
                    normalized_qid = qid if qid.startswith("Q") else f"Q{qid}"
                    qdash_value = qdash_values.get(normalized_qid, {}).get(param_name)

                    # Determine status
                    if qdash_value is None:
                        status = "new"
                    elif self._values_equal(yaml_value, qdash_value):
                        status = "same"
                    else:
                        status = "different"

                    param_comparison["qubits"][qid] = {
                        "yaml_value": yaml_value,
                        "qdash_value": qdash_value,
                        "status": status,
                    }

                result["parameters"][param_name] = param_comparison

            except Exception as e:
                logger.error(f"Failed to load {yaml_path}: {e}")
                continue

        return result

    def _values_equal(self, v1: Any, v2: Any, tolerance: float = 1e-9) -> bool:
        """Check if two values are equal within tolerance.

        Parameters
        ----------
        v1 : Any
            First value
        v2 : Any
            Second value
        tolerance : float
            Relative tolerance for float comparison

        Returns
        -------
        bool
            True if values are equal

        """
        if isinstance(v1, float) and isinstance(v2, float):
            if v1 == 0 and v2 == 0:
                return True
            if v1 == 0 or v2 == 0:
                return abs(v1 - v2) < tolerance
            return abs(v1 - v2) / max(abs(v1), abs(v2)) < tolerance
        return bool(v1 == v2)
