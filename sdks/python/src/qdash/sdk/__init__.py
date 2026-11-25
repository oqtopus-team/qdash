"""QDash SDK: the QDash API from Python, with calibration, workflow and dashboard helpers.

The SDK is distributed as ``qdash-sdk`` and is self-contained: it does not depend on
``qdash-client``. A :class:`QDash` session holds the configuration, authentication and
connection; it is the client, not a calibration session. ``QDash.api`` is the client of the
whole API, generated from its OpenAPI document; its response types are in
:mod:`qdash.sdk.types`. :class:`CalibrationSession` creates or opens a named calibration
session on a chip through a client and runs calibrations defined with :mod:`qdash.calibration`
(re-exported by :mod:`qdash.sdk.calibration`) in it, returning a
:class:`~qdash.calibration.CalibrationResult`; ``QDash.chip(chip_id)`` is the earlier
front door that starts a calibration in an automatic session;
``QDash.chips`` lists the project's chips and reads one chip's metadata;
``QDash.workflows`` lists, inspects and runs the workflows registered in the project;
``QDash.tasks`` reads the task catalog, loads a task's current parameters and runs one task
as the Task Workbench does;
``QDash.pipelines`` and :mod:`qdash.sdk.pipeline` work with whole pipeline specs;
``QDash.scripts`` and ``QDash.dashboards`` save metric scripts and dashboards defined with
:mod:`qdash.sdk.dashboard`; ``QDash.run(execution_id)`` follows any dispatched run;
``QDash.executions`` and ``QDash.task_results`` list past executions and task results one page
at a time, and ``QDash.execution(execution_id)`` and ``QDash.task_result(task_id)`` inspect
one execution or task result and its figures. ``QDash.device_topology`` computes the device
topology a device gateway publishes and draws it as a PNG, and ``QDash.qubex`` downloads the
Qubex configuration tree with the latest calibration note.
"""

from qdash.calibration import CalibrationResult, CalibrationRunError, CalibrationValidation
from qdash.sdk._calibration import CalibrationRun, Chip
from qdash.sdk._calibration_session import (
    CalibrationLaunch,
    CalibrationSession,
    CalibrationSessionClosedError,
)
from qdash.sdk._chips import Chips
from qdash.sdk._config import QDashConfig
from qdash.sdk._dashboards import Dashboards, SavedDashboard, SavedScript, Scripts
from qdash.sdk._device_topology import DeviceTopologies, DeviceTopology, DeviceTopologyPlot
from qdash.sdk._generated.client import AsyncQDashApi, QDashApi
from qdash.sdk._history import ExecutionHistory, ExecutionPage, TaskResultHistory, TaskResultPage
from qdash.sdk._parameters import Parameter, Parameters
from qdash.sdk._pipelines import PipelineRun, Pipelines
from qdash.sdk._qubex import Qubex, UnsafeArchiveError
from qdash.sdk._results import Artifact, Execution, ExecutionResult, Figure, TaskResult
from qdash.sdk._runs import Run, RunResult
from qdash.sdk._session import QDash
from qdash.sdk._tasks import TaskParameters, TaskRun, Tasks
from qdash.sdk._version import __version__, version
from qdash.sdk._workflows import (
    Workflow,
    WorkflowCancellation,
    WorkflowRun,
    WorkflowRunResult,
    Workflows,
)
from qdash.sdk.dashboard import Dashboard, MetricScriptError, Script, ScriptMetric
from qdash.sdk.errors import (
    ApiError,
    QDashApiError,
    QDashAuthError,
    QDashConfigDeprecationWarning,
    QDashConfigError,
    QDashConflictError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
)

__all__ = [
    "ApiError",
    "Artifact",
    "AsyncQDashApi",
    "CalibrationLaunch",
    "CalibrationResult",
    "CalibrationRun",
    "CalibrationRunError",
    "CalibrationSession",
    "CalibrationSessionClosedError",
    "CalibrationValidation",
    "Chip",
    "Chips",
    "Dashboard",
    "Dashboards",
    "DeviceTopologies",
    "DeviceTopology",
    "DeviceTopologyPlot",
    "Execution",
    "ExecutionHistory",
    "ExecutionPage",
    "ExecutionResult",
    "Figure",
    "MetricScriptError",
    "Parameter",
    "Parameters",
    "PipelineRun",
    "Pipelines",
    "QDash",
    "QDashApi",
    "QDashApiError",
    "QDashAuthError",
    "QDashConfig",
    "QDashConfigDeprecationWarning",
    "QDashConfigError",
    "QDashConflictError",
    "QDashNotFoundError",
    "QDashTransportError",
    "QDashValidationError",
    "Qubex",
    "Run",
    "RunResult",
    "SavedDashboard",
    "SavedScript",
    "Script",
    "ScriptMetric",
    "Scripts",
    "TaskParameters",
    "TaskResult",
    "TaskResultHistory",
    "TaskResultPage",
    "TaskRun",
    "Tasks",
    "UnsafeArchiveError",
    "Workflow",
    "WorkflowCancellation",
    "WorkflowRun",
    "WorkflowRunResult",
    "Workflows",
    "__version__",
    "version",
]
