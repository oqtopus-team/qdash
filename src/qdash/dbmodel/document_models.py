from typing import Any

from qdash.dbmodel.backend import BackendDocument
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.coupling_history import CouplingHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.flow import FlowDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.provenance import (
    ActivityDocument,
    ParameterVersionDocument,
    ProvenanceRelationDocument,
)
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.qubit_history import QubitHistoryDocument
from qdash.dbmodel.tag import TagDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.dbmodel.user import UserDocument


def document_models() -> list[Any]:
    """Initialize the repository and create initial data if needed."""
    return [
        ExecutionHistoryDocument,
        TaskResultHistoryDocument,
        QubitDocument,
        ChipDocument,
        TaskDocument,
        CouplingDocument,
        ProjectDocument,
        ProjectMembershipDocument,
        UserDocument,
        ExecutionCounterDocument,
        ExecutionLockDocument,
        TagDocument,
        CalibrationNoteDocument,
        QubitHistoryDocument,
        ChipHistoryDocument,
        CouplingHistoryDocument,
        BackendDocument,
        FlowDocument,
        # Provenance tracking
        ParameterVersionDocument,
        ProvenanceRelationDocument,
        ActivityDocument,
    ]
