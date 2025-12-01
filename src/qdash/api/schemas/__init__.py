"""API schema definitions."""

from qdash.api.schemas.auth import User, UserCreate
from qdash.api.schemas.backend import BackendResponseModel
from qdash.api.schemas.calibration import CalibrationNoteResponse
from qdash.api.schemas.chip import (
    ChipDatesResponse,
    ChipResponse,
    CreateChipRequest,
    ExecutionResponseDetail,
    ExecutionResponseSummary,
    LatestTaskGroupedByChipResponse,
    ListMuxResponse,
    MuxDetailResponse,
    Task,
    TaskHistoryResponse,
    TimeSeriesData,
    TimeSeriesProjection,
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
from qdash.api.schemas.execution import ExecutionLockStatusResponse
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
from qdash.api.schemas.parameter import ListParameterResponse
from qdash.api.schemas.success import SuccessResponse
from qdash.api.schemas.tag import ListTagResponse, Tag
from qdash.api.schemas.task import (
    InputParameterModel,
    ListTaskResponse,
    TaskResponse,
    TaskResultResponse,
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
    "ExecutionResponseDetail",
    "ExecutionResponseSummary",
    "LatestTaskGroupedByChipResponse",
    "ListMuxResponse",
    "MuxDetailResponse",
    "Task",
    "TaskHistoryResponse",
    "TimeSeriesData",
    "TimeSeriesProjection",
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
    # parameter
    "ListParameterResponse",
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
]
