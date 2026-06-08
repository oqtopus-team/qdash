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
    MetricHistoryItem,
    MetricValue,
    QubitMetricHistoryResponse,
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
    TaskResultListItem,
    TaskResultListResponse,
    TimeSeriesData,
    TimeSeriesProjection,
)

__all__ = [
    # backend
    "BackendResponseModel",
    # calibration
    "CalibrationNoteResponse",
    # chip
    "ChipDatesResponse",
    # metrics
    "ChipMetricsResponse",
    "ChipResponse",
    # device_topology
    "Condition",
    "Coupling",
    "CouplingGateDuration",
    "CreateChipRequest",
    # flow
    "DeleteScheduleResponse",
    # error
    "Detail",
    "Device",
    "DeviceTopologyRequest",
    "ExecuteFlowRequest",
    "ExecuteFlowResponse",
    # execution
    "ExecutionLockStatusResponse",
    "ExecutionResponseDetail",
    "ExecutionResponseSummary",
    "FidelityCondition",
    # file
    "FileTreeNode",
    "FlowScheduleSummary",
    "FlowSummary",
    "FlowTemplate",
    "FlowTemplateWithCode",
    "GetFlowResponse",
    "GitPushRequest",
    # task
    "InputParameterModel",
    "InternalServerError",
    # task_result
    "LatestTaskResultResponse",
    "ListFlowSchedulesResponse",
    "ListFlowsResponse",
    "ListMuxResponse",
    # tag
    "ListTagResponse",
    "ListTaskResponse",
    "MeasError",
    "MetricHistoryItem",
    "MetricValue",
    "MuxDetailResponse",
    "MuxTask",
    "Position",
    "Qubit",
    "QubitGateDuration",
    "QubitLifetime",
    "QubitMetricHistoryResponse",
    "SaveFileRequest",
    "SaveFlowRequest",
    "SaveFlowResponse",
    "ScheduleFlowRequest",
    "ScheduleFlowResponse",
    # success
    "SuccessResponse",
    "Tag",
    "Task",
    "TaskHistoryResponse",
    "TaskResponse",
    "TaskResult",
    "TaskResultListItem",
    "TaskResultListResponse",
    "TaskResultResponse",
    "TimeSeriesData",
    "TimeSeriesProjection",
    "UpdateScheduleRequest",
    "UpdateScheduleResponse",
    # auth
    "User",
    "UserCreate",
    "ValidateFileRequest",
]
