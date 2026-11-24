"""QDash SDK: the QDash API from Python, with calibration, workflow and dashboard helpers.

The SDK is distributed as ``qdash-sdk`` and is self-contained: it does not depend on
``qdash-client``. A :class:`QDash` session holds the configuration, authentication and
connection. ``QDash.api`` is the client of the whole API, generated from its OpenAPI document;
its response types are in :mod:`qdash.sdk.types`. On top of it, ``QDash.chip(chip_id)``
validates and starts calibrations defined with :mod:`qdash.sdk.calibration`;
``QDash.workflows`` lists, inspects and runs the workflows registered in the project;
``QDash.pipelines`` and :mod:`qdash.sdk.pipeline` work with whole pipeline specs;
``QDash.scripts`` and ``QDash.dashboards`` save metric scripts and dashboards defined with
:mod:`qdash.sdk.dashboard`; ``QDash.run(execution_id)`` follows any dispatched run.
"""

from qdash.sdk._calibration import CalibrationRun, Chip
from qdash.sdk._config import QDashConfig
from qdash.sdk._dashboards import Dashboards, SavedDashboard, SavedScript, Scripts
from qdash.sdk._generated.client import AsyncQDashApi, QDashApi
from qdash.sdk._pipelines import PipelineRun, Pipelines
from qdash.sdk._runs import Run, RunResult
from qdash.sdk._session import QDash
from qdash.sdk._workflows import Workflow, WorkflowRun, Workflows
from qdash.sdk.dashboard import Dashboard, MetricScriptError, Script, ScriptMetric
from qdash.sdk.errors import (
    ApiError,
    QDashApiError,
    QDashAuthError,
    QDashConfigError,
    QDashConflictError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
)

__all__ = [
    "ApiError",
    "AsyncQDashApi",
    "CalibrationRun",
    "Chip",
    "Dashboard",
    "Dashboards",
    "MetricScriptError",
    "PipelineRun",
    "Pipelines",
    "QDash",
    "QDashApi",
    "QDashApiError",
    "QDashAuthError",
    "QDashConfig",
    "QDashConfigError",
    "QDashConflictError",
    "QDashNotFoundError",
    "QDashTransportError",
    "QDashValidationError",
    "Run",
    "RunResult",
    "SavedDashboard",
    "SavedScript",
    "Script",
    "ScriptMetric",
    "Scripts",
    "Workflow",
    "WorkflowRun",
    "Workflows",
]
