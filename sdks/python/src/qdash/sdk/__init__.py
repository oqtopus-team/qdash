"""QDash SDK: define calibrations in Python and run them through the QDash API.

The SDK is distributed as ``qdash-sdk``, which depends on ``qdash-client`` and reuses its
configuration, authentication, transport and errors. ``QDash.chip(chip_id)`` validates and
starts calibrations defined with :mod:`qdash.sdk.calibration`; ``QDash.workflows`` lists,
inspects and runs the workflows registered in the project; ``QDash.pipelines`` and
:mod:`qdash.sdk.pipeline` work with whole pipeline specs.
"""

from qdash.client.services.errors import (
    QDashApiError,
    QDashAuthError,
    QDashConfigError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
)
from qdash.sdk._calibration import CalibrationRun, Chip
from qdash.sdk._pipelines import PipelineRun, Pipelines
from qdash.sdk._runs import RunResult
from qdash.sdk._session import QDash
from qdash.sdk._workflows import Workflow, WorkflowRun, Workflows

__all__ = [
    "CalibrationRun",
    "Chip",
    "PipelineRun",
    "Pipelines",
    "QDash",
    "QDashApiError",
    "QDashAuthError",
    "QDashConfigError",
    "QDashNotFoundError",
    "QDashTransportError",
    "QDashValidationError",
    "RunResult",
    "Workflow",
    "WorkflowRun",
    "Workflows",
]
