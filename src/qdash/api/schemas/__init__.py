"""API Schemas.

Defines request/response types for FastAPI endpoints.
TypeScript types for the frontend are auto-generated based on OpenAPI spec.

Related modules:
- datamodel: Domain models for business logic
- dbmodel: MongoDB persistence models

Note: Run `task generate` to regenerate frontend types after modifying this directory.
"""

from qdash.api.schemas.auth import User, UserCreate
from qdash.api.schemas.backend import BackendResponseModel
from qdash.api.schemas.calibration import CalibrationNoteResponse
from qdash.api.schemas.chip import (
    ChipDatesResponse,
    ChipResponse,
    CreateChipRequest,
    ListMuxResponse,
    MuxDetailResponse,
    MuxTask,
)
from qdash.api.schemas.device_topology import (
    Condition,
    Coupling,
    CouplingGateDuration,
    Device,
    DeviceTopologyRequest,
    FidelityCondition,
    MeasError,
    Position,
    Qubit,
    QubitGateDuration,
    QubitLifetime,
)
from qdash.api.schemas.error import Detail, InternalServerError
from qdash.api.schemas.execution import (
    ExecutionLockStatusResponse,
    ExecutionResponseDetail,
    ExecutionResponseSummary,
    Task,
)
from qdash.api.schemas.file import (
    FileTreeNode,
    GitPushRequest,
    SaveFileRequest,
    ValidateFileRequest,
)
from qdash.api.schemas.flow import (
    DeleteScheduleResponse,
    ExecuteFlowRequest,
    ExecuteFlowResponse,
    FlowScheduleSummary,
    FlowSummary,
    FlowTemplate,
    FlowTemplateWithCode,
    GetFlowResponse,
    ListFlowSchedulesResponse,
    ListFlowsResponse,
    SaveFlowRequest,
    SaveFlowResponse,
    ScheduleFlowRequest,
    ScheduleFlowResponse,
    UpdateScheduleRequest,
    UpdateScheduleResponse,
)
from qdash.api.schemas.metrics import (
    ChipMetricsResponse,
    CouplingMetrics,
    MetricHistoryItem,
    MetricValue,
    QubitMetricHistoryResponse,
    QubitMetrics,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.schemas.tag import ListTagResponse, Tag
from qdash.api.schemas.task import (
    InputParameterModel,
    ListTaskResponse,
    TaskResponse,
    TaskResultResponse,
)
from qdash.api.schemas.task_result import (
    LatestTaskResultResponse,
    TaskHistoryResponse,
    TaskResult,
    TimeSeriesData,
    TimeSeriesProjection,
)

__all__ = [
    # auth
    "User",
    "UserCreate",
    # backend
    "BackendResponseModel",
    # calibration
    "CalibrationNoteResponse",
    # chip
    "ChipDatesResponse",
    "ChipResponse",
    "CreateChipRequest",
    "ListMuxResponse",
    "MuxDetailResponse",
    "MuxTask",
    # device_topology
    "Condition",
    "Coupling",
    "CouplingGateDuration",
    "Device",
    "DeviceTopologyRequest",
    "FidelityCondition",
    "MeasError",
    "Position",
    "Qubit",
    "QubitGateDuration",
    "QubitLifetime",
    # error
    "Detail",
    "InternalServerError",
    # execution
    "ExecutionLockStatusResponse",
    "ExecutionResponseDetail",
    "ExecutionResponseSummary",
    "Task",
    # file
    "FileTreeNode",
    "GitPushRequest",
    "SaveFileRequest",
    "ValidateFileRequest",
    # flow
    "DeleteScheduleResponse",
    "ExecuteFlowRequest",
    "ExecuteFlowResponse",
    "FlowScheduleSummary",
    "FlowSummary",
    "FlowTemplate",
    "FlowTemplateWithCode",
    "GetFlowResponse",
    "ListFlowSchedulesResponse",
    "ListFlowsResponse",
    "SaveFlowRequest",
    "SaveFlowResponse",
    "ScheduleFlowRequest",
    "ScheduleFlowResponse",
    "UpdateScheduleRequest",
    "UpdateScheduleResponse",
    # metrics
    "ChipMetricsResponse",
    "CouplingMetrics",
    "MetricHistoryItem",
    "MetricValue",
    "QubitMetricHistoryResponse",
    "QubitMetrics",
    # success
    "SuccessResponse",
    # tag
    "ListTagResponse",
    "Tag",
    # task
    "InputParameterModel",
    "ListTaskResponse",
    "TaskResponse",
    "TaskResultResponse",
    # task_result
    "LatestTaskResultResponse",
    "TaskHistoryResponse",
    "TaskResult",
    "TimeSeriesData",
    "TimeSeriesProjection",
]
