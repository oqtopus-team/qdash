from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any, TypeVar, cast

import httpx
from pydantic import BaseModel, ValidationError

from qdash.client.rest.api_client import ApiClient as RestApiClient
from qdash.client.rest.configuration import Configuration as RestConfiguration
from qdash.client.rest.exceptions import ApiException as RestApiException

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from qdash.client.rest.api_response import ApiResponse as RestApiResponse
from qdash.client.services.config import QDashConfig
from qdash.client.services.errors import (
    QDashApiError,
    QDashAuthError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
)
from qdash.client.services.exporter_models import NormalizedMetricRecord
from qdash.client.services.models import (
    AgentActionListResponse,
    AgentActionResponse,
    AgentCandidateCommitResponse,
    AgentCandidateListResponse,
    AgentCandidateResponse,
    AgentSessionResponse,
    AiReviewListResponse,
    AiReviewRunDetailResponse,
    AiReviewRunListResponse,
    BodyReExecuteTaskResult,
    CancelExecutionResponse,
    CandidateGateResponse,
    ChipMetricsResponse,
    ChipResponse,
    CouplingResponse,
    ExecuteFlowResponse,
    ExecutionResponseDetail,
    FileTreeNode,
    FlowTemplate,
    FlowTemplateWithCode,
    GetFlowResponse,
    ImpactResponse,
    IssueKnowledgeResponse,
    IssueResponse,
    LatestTaskResultResponse,
    LineageResponse,
    ListChipsResponse,
    ListCouplingsResponse,
    ListExecutionsResponse,
    ListFlowsResponse,
    ListIssueKnowledgeResponse,
    ListIssuesResponse,
    ListQubitsResponse,
    ListTaskKnowledgeResponse,
    ListTaskResponse,
    NoteModel,
    ParameterHistoryResponse,
    ParameterVersionResponse,
    ProjectResponse,
    ProvenanceStatsResponse,
    QdashApiSchemasProjectProjectListResponse,
    QubitResponse,
    RecentChangesResponse,
    SaveFlowResponse,
    ScheduleFlowResponse,
    SuccessResponse,
    TaskHistoryResponse,
    TaskKnowledgeResponse,
    TaskResultExcludeResponse,
    TaskResultListResponse,
    TaskResultResponse,
    TimeSeriesData,
)

PACKAGE_NAME = "qdash"
TModel = TypeVar("TModel", bound=BaseModel)


def _resolve_user_agent() -> str:
    try:
        package_version = version(PACKAGE_NAME)
    except PackageNotFoundError:
        package_version = "unknown"
    return f"qdash-client/{package_version}"


class QDashClient:
    """HTTP client for interacting with the QDash API."""

    def __init__(
        self,
        config: QDashConfig | None = None,
        *,
        http_client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.config = config or QDashConfig.from_file()
        self._sleep = sleep_fn or time.sleep
        self._rest_client = RestApiClient(
            RestConfiguration(
                host=self.config.base_url,
                timeout=self.config.timeout_sec,
                verify_tls=self.config.verify_tls,
                proxy=self.config.proxy,
            ),
            http_client=http_client,
        )
        self._default_headers = default_headers or {}

        self._token: str | None = self.config.api_token
        if not self.config.user_agent or self.config.user_agent == "qdash-client/dev":
            self.config.user_agent = _resolve_user_agent()

    @classmethod
    def from_env(cls) -> QDashClient:
        """Create a client from QDash environment variables."""

        return cls(QDashConfig.from_env())

    @classmethod
    def from_profile(cls, profile: str = "default", path: str | Path | None = None) -> QDashClient:
        """Create a client from a named config file profile."""

        config = (
            QDashConfig.from_file(profile=profile)
            if path is None
            else QDashConfig.from_file(profile=profile, path=path)
        )
        return cls(config)

    def close(self) -> None:
        self._rest_client.close()

    def _validate_model_payload(
        self,
        model_type: type[TModel],
        payload: Any,
    ) -> TModel:
        if isinstance(payload, dict):
            normalized_payload = self._normalize_datetime_fields(payload)
            try:
                return model_type.model_validate(normalized_payload)
            except ValidationError as exc:
                raise QDashValidationError(
                    f"Response payload did not match {model_type.__name__}",
                    payload=payload,
                ) from exc
        raise QDashValidationError(
            f"Response payload did not match {model_type.__name__}",
            payload=payload,
        )

    def _validate_model_list_payload(
        self,
        model_type: type[TModel],
        payload: Any,
    ) -> list[TModel]:
        if isinstance(payload, list):
            try:
                return [
                    item if isinstance(item, model_type) else model_type.model_validate(item)
                    for item in self._normalize_datetime_fields(payload)
                ]
            except ValidationError as exc:
                raise QDashValidationError(
                    f"Response payload did not match list[{model_type.__name__}]",
                    payload=payload,
                ) from exc
        raise QDashValidationError(
            f"Response payload did not match list[{model_type.__name__}]",
            payload=payload,
        )

    def _normalize_datetime_fields(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            normalized: dict[str, Any] = {}
            for key, value in payload.items():
                if isinstance(value, str) and key.endswith("_at"):
                    normalized[key] = self._normalize_datetime_string(value)
                elif key == "error" and value is None:
                    normalized[key] = 0
                else:
                    normalized[key] = self._normalize_datetime_fields(value)
            return normalized
        if isinstance(payload, list):
            return [self._normalize_datetime_fields(item) for item in payload]
        return payload

    def _normalize_datetime_string(self, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if parsed.tzinfo is None:
            return f"{value}+00:00"
        return value

    def _empty_chip_metrics(self) -> ChipMetricsResponse:
        return ChipMetricsResponse(
            chip_id="",
            username="",
            qubit_count=0,
            within_hours=None,
            start_at=None,
            end_at=None,
            qubit_metrics={},
            coupling_metrics={},
        )

    def _coerce_chip_metrics_payload(self, payload: dict[str, Any]) -> ChipMetricsResponse:
        # Keep backward compatibility with looser payloads that are still useful to callers.
        qubit_metrics = payload.get("qubit_metrics")
        coupling_metrics = payload.get("coupling_metrics")
        return ChipMetricsResponse.model_construct(
            chip_id=str(payload.get("chip_id") or ""),
            username=str(payload.get("username") or ""),
            qubit_count=int(payload.get("qubit_count", 0) or 0),
            within_hours=(
                int(payload["within_hours"]) if payload.get("within_hours") is not None else None
            ),
            start_at=payload.get("start_at"),
            end_at=payload.get("end_at"),
            qubit_metrics=cast("dict[str, Any]", qubit_metrics)
            if isinstance(qubit_metrics, dict)
            else {},
            coupling_metrics=cast("dict[str, Any]", coupling_metrics)
            if isinstance(coupling_metrics, dict)
            else {},
        )

    def list_chips(self) -> ListChipsResponse:
        response = self._request("GET", "/chips")
        return self._validate_model_payload(
            ListChipsResponse,
            response.data,
        )

    def get_default_chip(self) -> ChipResponse:
        """Return the default chip, preferring the latest active chip when available."""

        chips = self.list_chips().chips
        if chips:
            active_chips = [chip for chip in chips if str(chip.activity_status) == "active"]
            candidates = active_chips or chips
            return max(
                candidates,
                key=lambda chip: (
                    chip.installed_at is not None,
                    chip.installed_at or datetime.min.replace(tzinfo=UTC),
                ),
            )
        raise QDashNotFoundError("No chips found.")

    def get_default_chip_id(self) -> str:
        """Return the default chip ID, preferring the latest active chip when available."""

        return self.get_default_chip().chip_id

    def get_chip_metrics(self, chip_id: str) -> ChipMetricsResponse:
        response = self._request("GET", f"/metrics/chips/{chip_id}/metrics")
        data = response.data
        if isinstance(data, dict):
            normalized_data = self._normalize_datetime_fields(data)
            try:
                return ChipMetricsResponse.model_validate(normalized_data)
            except ValidationError:
                return self._coerce_chip_metrics_payload(normalized_data)
        return self._empty_chip_metrics()

    def get_metrics_config(self) -> dict[str, Any]:
        response = self._request("GET", "/metrics/config")
        data = response.data
        return data if isinstance(data, dict) else {}

    def list_chip_qubits(
        self,
        chip_id: str,
        *,
        qids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> ListQubitsResponse:
        params = self._query_params(qids=qids, offset=offset, limit=limit)
        response = self._request("GET", f"/chips/{chip_id}/qubits", params=params)
        return self._validate_model_payload(ListQubitsResponse, response.data)

    def get_chip_qubit(self, chip_id: str, qid: str) -> QubitResponse:
        response = self._request("GET", f"/chips/{chip_id}/qubits/{qid}")
        return self._validate_model_payload(QubitResponse, response.data)

    def list_chip_couplings(
        self,
        chip_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> ListCouplingsResponse:
        response = self._request(
            "GET",
            f"/chips/{chip_id}/couplings",
            params={"offset": offset, "limit": limit},
        )
        return self._validate_model_payload(ListCouplingsResponse, response.data)

    def get_chip_coupling(self, chip_id: str, coupling_id: str) -> CouplingResponse:
        response = self._request("GET", f"/chips/{chip_id}/couplings/{coupling_id}")
        return self._validate_model_payload(CouplingResponse, response.data)

    def get_task_results_timeseries(
        self,
        *,
        chip_id: str,
        parameter: str,
        tag: str | None = None,
        qid: str | None = None,
        start_at: str,
        end_at: str,
    ) -> TimeSeriesData:
        params: dict[str, Any] = {
            "chip_id": chip_id,
            "parameter": parameter,
            "start_at": start_at,
            "end_at": end_at,
        }
        if tag:
            params["tag"] = tag
        if qid:
            params["qid"] = qid

        response = self._request("GET", "/task-results/timeseries", params=params)
        return self._validate_model_payload(
            TimeSeriesData,
            response.data,
        )

    def list_task_results(
        self,
        *,
        status: str | None = None,
        chip_id: str | None = None,
        task_name: str | None = None,
        qid: str | None = None,
        execution_id: str | None = None,
        username: str | None = None,
        start_from: str | None = None,
        start_to: str | None = None,
        message_contains: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> TaskResultListResponse:
        params = self._query_params(
            status=status,
            chip_id=chip_id,
            task_name=task_name,
            qid=qid,
            execution_id=execution_id,
            username=username,
            start_from=start_from,
            start_to=start_to,
            message_contains=message_contains,
            skip=skip,
            limit=limit,
        )
        response = self._request("GET", "/task-results", params=params)
        return self._validate_model_payload(TaskResultListResponse, response.data)

    def get_qubit_latest_task_results(
        self,
        *,
        chip_id: str,
        task: str,
    ) -> LatestTaskResultResponse:
        response = self._request(
            "GET",
            "/task-results/qubits/latest",
            params={"chip_id": chip_id, "task": task},
        )
        return self._validate_model_payload(LatestTaskResultResponse, response.data)

    def get_qubit_task_history(
        self,
        *,
        qid: str,
        chip_id: str,
        task: str,
        date: str,
    ) -> TaskHistoryResponse:
        response = self._request(
            "GET",
            f"/task-results/qubits/{qid}/history",
            params={"chip_id": chip_id, "task": task, "date": date},
        )
        return self._validate_model_payload(TaskHistoryResponse, response.data)

    def get_coupling_latest_task_results(
        self,
        *,
        chip_id: str,
        task: str,
    ) -> LatestTaskResultResponse:
        response = self._request(
            "GET",
            "/task-results/couplings/latest",
            params={"chip_id": chip_id, "task": task},
        )
        return self._validate_model_payload(LatestTaskResultResponse, response.data)

    def get_coupling_task_history(
        self,
        *,
        coupling_id: str,
        chip_id: str,
        task: str,
        date: str,
    ) -> TaskHistoryResponse:
        response = self._request(
            "GET",
            f"/task-results/couplings/{coupling_id}/history",
            params={"chip_id": chip_id, "task": task, "date": date},
        )
        return self._validate_model_payload(TaskHistoryResponse, response.data)

    def list_projects(self) -> QdashApiSchemasProjectProjectListResponse:
        response = self._request("GET", "/projects")
        return self._validate_model_payload(
            QdashApiSchemasProjectProjectListResponse,
            response.data,
        )

    def get_project(self, project_id: str) -> ProjectResponse:
        response = self._request("GET", f"/projects/{project_id}")
        return self._validate_model_payload(ProjectResponse, response.data)

    def get_files_tree(self) -> list[FileTreeNode]:
        response = self._request("GET", "/files/tree")
        return self._validate_model_list_payload(FileTreeNode, response.data)

    def get_file_content(self, path: str) -> dict[str, Any]:
        response = self._request("GET", "/files/content", params={"path": path})
        data = response.data
        return data if isinstance(data, dict) else {}

    def get_git_status(self) -> dict[str, Any]:
        response = self._request("GET", "/files/git/status")
        data = response.data
        return data if isinstance(data, dict) else {}

    def save_file_content(self, *, path: str, content: str) -> dict[str, Any]:
        response = self._request(
            "PUT",
            "/files/content",
            json={"path": path, "content": content},
        )
        data = response.data
        return data if isinstance(data, dict) else {}

    def validate_file_content(self, *, content: str, file_type: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/files/validate",
            json={"content": content, "file_type": file_type},
        )
        data = response.data
        return data if isinstance(data, dict) else {}

    def git_pull_config(self) -> dict[str, Any]:
        response = self._request("POST", "/files/git/pull", json={})
        data = response.data
        return data if isinstance(data, dict) else {}

    def git_push_config(
        self,
        *,
        commit_message: str = "Update config files from UI",
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/files/git/push",
            json={"commit_message": commit_message},
        )
        data = response.data
        return data if isinstance(data, dict) else {}

    def list_issues(
        self,
        *,
        task_id: str | None = None,
        is_closed: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> ListIssuesResponse:
        params = self._query_params(
            task_id=task_id,
            is_closed=is_closed,
            skip=skip,
            limit=limit,
        )
        response = self._request("GET", "/issues", params=params)
        return self._validate_model_payload(ListIssuesResponse, response.data)

    def get_issue(self, issue_id: str) -> IssueResponse:
        response = self._request("GET", f"/issues/{issue_id}")
        return self._validate_model_payload(IssueResponse, response.data)

    def list_task_result_issues(self, task_id: str) -> list[IssueResponse]:
        response = self._request("GET", f"/task-results/{task_id}/issues")
        return self._validate_model_list_payload(IssueResponse, response.data)

    def create_task_result_issue(
        self,
        *,
        task_id: str,
        content: str,
        title: str | None = None,
        parent_id: str | None = None,
    ) -> IssueResponse:
        response = self._request(
            "POST",
            f"/task-results/{task_id}/issues",
            json=self._query_params(title=title, content=content, parent_id=parent_id),
        )
        return self._validate_model_payload(IssueResponse, response.data)

    def update_issue(
        self,
        issue_id: str,
        *,
        content: str,
        title: str | None = None,
    ) -> IssueResponse:
        response = self._request(
            "PATCH",
            f"/issues/{issue_id}",
            json=self._query_params(title=title, content=content),
        )
        return self._validate_model_payload(IssueResponse, response.data)

    def close_issue(self, issue_id: str) -> SuccessResponse:
        response = self._request("PATCH", f"/issues/{issue_id}/close", json={})
        return self._validate_model_payload(SuccessResponse, response.data)

    def reopen_issue(self, issue_id: str) -> SuccessResponse:
        response = self._request("PATCH", f"/issues/{issue_id}/reopen", json={})
        return self._validate_model_payload(SuccessResponse, response.data)

    def list_issue_knowledge(
        self,
        *,
        status: str | None = None,
        task_name: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> ListIssueKnowledgeResponse:
        params = self._query_params(
            status=status,
            task_name=task_name,
            skip=skip,
            limit=limit,
        )
        response = self._request("GET", "/issue-knowledge", params=params)
        return self._validate_model_payload(ListIssueKnowledgeResponse, response.data)

    def get_issue_knowledge(self, knowledge_id: str) -> IssueKnowledgeResponse:
        response = self._request("GET", f"/issue-knowledge/{knowledge_id}")
        return self._validate_model_payload(IssueKnowledgeResponse, response.data)

    def update_issue_knowledge(
        self,
        knowledge_id: str,
        *,
        fields: dict[str, Any],
    ) -> IssueKnowledgeResponse:
        response = self._request(
            "PATCH",
            f"/issue-knowledge/{knowledge_id}",
            json=fields,
        )
        return self._validate_model_payload(IssueKnowledgeResponse, response.data)

    def approve_issue_knowledge(self, knowledge_id: str) -> IssueKnowledgeResponse:
        response = self._request("PATCH", f"/issue-knowledge/{knowledge_id}/approve", json={})
        return self._validate_model_payload(IssueKnowledgeResponse, response.data)

    def reject_issue_knowledge(self, knowledge_id: str) -> IssueKnowledgeResponse:
        response = self._request("PATCH", f"/issue-knowledge/{knowledge_id}/reject", json={})
        return self._validate_model_payload(IssueKnowledgeResponse, response.data)

    def extract_issue_knowledge(self, issue_id: str) -> IssueKnowledgeResponse:
        response = self._request("POST", f"/issues/{issue_id}/extract-knowledge", json={})
        return self._validate_model_payload(IssueKnowledgeResponse, response.data)

    def list_flows(self) -> ListFlowsResponse:
        response = self._request("GET", "/flows")
        return self._validate_model_payload(ListFlowsResponse, response.data)

    def get_flow(self, name: str) -> GetFlowResponse:
        response = self._request("GET", f"/flows/{name}")
        return self._validate_model_payload(GetFlowResponse, response.data)

    def list_flow_templates(self) -> list[FlowTemplate]:
        response = self._request("GET", "/flows/templates")
        return self._validate_model_list_payload(FlowTemplate, response.data)

    def get_flow_template(self, template_id: str) -> FlowTemplateWithCode:
        response = self._request("GET", f"/flows/templates/{template_id}")
        return self._validate_model_payload(FlowTemplateWithCode, response.data)

    def list_flow_helper_files(self) -> list[str]:
        response = self._request("GET", "/flows/helpers")
        data = response.data
        return [str(item) for item in data] if isinstance(data, list) else []

    def get_flow_helper_file(self, filename: str) -> str:
        response = self._request("GET", f"/flows/helpers/{filename}")
        return response.data if isinstance(response.data, str) else ""

    def save_flow(
        self,
        *,
        name: str,
        code: str,
        chip_id: str,
        description: str = "",
        flow_function_name: str | None = None,
        default_parameters: dict[str, Any] | None = None,
        default_run_parameters: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> SaveFlowResponse:
        response = self._request(
            "POST",
            "/flows",
            json=self._query_params(
                name=name,
                description=description,
                code=code,
                flow_function_name=flow_function_name,
                chip_id=chip_id,
                default_parameters=default_parameters,
                default_run_parameters=default_run_parameters,
                tags=tags,
            ),
        )
        return self._validate_model_payload(SaveFlowResponse, response.data)

    def execute_flow(
        self,
        name: str,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> ExecuteFlowResponse:
        response = self._request(
            "POST",
            f"/flows/{name}/execute",
            json={"parameters": parameters},
        )
        return self._validate_model_payload(ExecuteFlowResponse, response.data)

    def schedule_flow(
        self,
        name: str,
        *,
        cron: str | None = None,
        scheduled_time: str | None = None,
        parameters: dict[str, Any] | None = None,
        active: bool = True,
        timezone: str = "Asia/Tokyo",
    ) -> ScheduleFlowResponse:
        response = self._request(
            "POST",
            f"/flows/{name}/schedule",
            json=self._query_params(
                cron=cron,
                scheduled_time=scheduled_time,
                parameters=parameters,
                active=active,
                timezone=timezone,
            ),
        )
        return self._validate_model_payload(ScheduleFlowResponse, response.data)

    def list_executions(
        self,
        *,
        chip_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> ListExecutionsResponse:
        response = self._request(
            "GET",
            "/executions",
            params={"chip_id": chip_id, "skip": skip, "limit": limit},
        )
        return self._validate_model_payload(ListExecutionsResponse, response.data)

    def get_execution(self, execution_id: str) -> ExecutionResponseDetail:
        response = self._request("GET", f"/executions/{execution_id}")
        return self._validate_model_payload(ExecutionResponseDetail, response.data)

    def wait_for_execution(
        self,
        execution_id: str,
        *,
        timeout_seconds: float = 600.0,
        poll_interval_seconds: float = 1.0,
        terminal_statuses: set[str] | None = None,
    ) -> ExecutionResponseDetail:
        """Poll an execution until it reaches a terminal state or times out."""
        if timeout_seconds < 0 or poll_interval_seconds < 0:
            raise ValueError("Polling timeout and interval must be non-negative")
        terminal = terminal_statuses or {"completed", "failed", "cancelled"}
        deadline = time.monotonic() + timeout_seconds

        while True:
            try:
                execution = self.get_execution(execution_id)
            except QDashNotFoundError:
                execution = None
            if execution is not None and execution.status.lower() in terminal:
                return execution
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Execution '{execution_id}' did not reach a terminal state "
                    f"within {timeout_seconds} seconds"
                )
            self._sleep(poll_interval_seconds)

    def create_agent_session(
        self,
        *,
        chip_id: str,
        policy: dict[str, Any],
        expires_in_seconds: int = 21_600,
        skill_name: str = "",
        skill_version: str = "",
        skill_hash: str = "",
        model_name: str = "",
    ) -> AgentSessionResponse:
        """Create a bounded authorization session for a local agent."""
        response = self._request(
            "POST",
            "/agent-sessions",
            json={
                "chip_id": chip_id,
                "policy": policy,
                "expires_in_seconds": expires_in_seconds,
                "skill_name": skill_name,
                "skill_version": skill_version,
                "skill_hash": skill_hash,
                "model_name": model_name,
            },
        )
        return self._validate_model_payload(AgentSessionResponse, response.data)

    def get_agent_session(self, session_id: str) -> AgentSessionResponse:
        """Get authoritative state for a local-agent session."""
        response = self._request("GET", f"/agent-sessions/{session_id}")
        return self._validate_model_payload(AgentSessionResponse, response.data)

    def evaluate_agent_candidate_gate(
        self,
        session_id: str,
        *,
        parameter_name: str,
        value: float,
    ) -> CandidateGateResponse:
        """Evaluate a candidate using the immutable bounds owned by the session."""
        response = self._request(
            "POST",
            f"/agent-sessions/{session_id}/candidate-gate",
            json={"parameter_name": parameter_name, "value": value},
        )
        return self._validate_model_payload(CandidateGateResponse, response.data)

    def submit_agent_action(
        self,
        session_id: str,
        *,
        idempotency_key: str,
        expected_state_version: int,
        action_type: str,
        task_name: str | None = None,
        qids: list[str] | None = None,
        parameter_overrides: dict[str, float] | None = None,
        diagnosis: str = "",
    ) -> AgentActionResponse:
        """Submit a policy-checked action proposal for a local-agent session."""
        response = self._request(
            "POST",
            f"/agent-sessions/{session_id}/actions",
            json={
                "idempotency_key": idempotency_key,
                "expected_state_version": expected_state_version,
                "action_type": action_type,
                "task_name": task_name,
                "qids": qids or [],
                "parameter_overrides": parameter_overrides or {},
                "diagnosis": diagnosis,
            },
        )
        return self._validate_model_payload(AgentActionResponse, response.data)

    def execute_agent_action(
        self,
        session_id: str,
        action_id: str,
        *,
        source_execution_id: str,
        update_params: bool = False,
        reconfigure: bool = False,
    ) -> AgentActionResponse:
        """Dispatch one authorized agent action to the system workflow."""
        response = self._request(
            "POST",
            f"/agent-sessions/{session_id}/actions/{action_id}/execute",
            json={
                "source_execution_id": source_execution_id,
                "update_params": update_params,
                "reconfigure": reconfigure,
            },
        )
        return self._validate_model_payload(AgentActionResponse, response.data)

    def get_agent_action(self, session_id: str, action_id: str) -> AgentActionResponse:
        """Get one action for polling dispatch status and operation ID."""
        response = self._request("GET", f"/agent-sessions/{session_id}/actions/{action_id}")
        return self._validate_model_payload(AgentActionResponse, response.data)

    def wait_for_agent_action(
        self,
        session_id: str,
        action_id: str,
        *,
        timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 0.5,
    ) -> AgentActionResponse:
        """Poll until action dispatch produces an operation ID or fails."""
        if timeout_seconds < 0 or poll_interval_seconds < 0:
            raise ValueError("Polling timeout and interval must be non-negative")
        deadline = time.monotonic() + timeout_seconds

        while True:
            action = self.get_agent_action(session_id, action_id)
            if action.execution_status == "failed":
                return action
            if action.operation_id is not None:
                return action
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Agent action '{action_id}' did not produce an operation "
                    f"within {timeout_seconds} seconds"
                )
            self._sleep(poll_interval_seconds)

    def wait_for_agent_action_execution(
        self,
        session_id: str,
        action_id: str,
        *,
        timeout_seconds: float = 600.0,
        poll_interval_seconds: float = 0.5,
    ) -> AgentActionResponse:
        """Poll until a Prefect operation is linked to its QDash execution."""
        if timeout_seconds < 0 or poll_interval_seconds < 0:
            raise ValueError("Polling timeout and interval must be non-negative")
        deadline = time.monotonic() + timeout_seconds

        while True:
            action = self.get_agent_action(session_id, action_id)
            if action.execution_status == "failed":
                return action
            if action.execution_id is not None:
                return action
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Agent action {action_id} did not produce a QDash execution "
                    f"within {timeout_seconds} seconds"
                )
            self._sleep(poll_interval_seconds)

    def list_agent_action_candidates(
        self,
        session_id: str,
        action_id: str,
    ) -> list[AgentCandidateResponse]:
        """List candidates derived from an action's authoritative task result."""
        response = self._request(
            "GET",
            f"/agent-sessions/{session_id}/actions/{action_id}/candidates",
        )
        payload = self._validate_model_payload(AgentCandidateListResponse, response.data)
        return payload.items

    def commit_agent_action_candidate(
        self,
        session_id: str,
        action_id: str,
        parameter_name: str,
        *,
        idempotency_key: str,
        expected_state_version: int,
        task_id: str,
    ) -> AgentCandidateCommitResponse:
        """Commit a revalidated task-result candidate into QDash calibration state."""
        response = self._request(
            "POST",
            (
                f"/agent-sessions/{session_id}/actions/{action_id}"
                f"/candidates/{parameter_name}/commit"
            ),
            json={
                "idempotency_key": idempotency_key,
                "expected_state_version": expected_state_version,
                "task_id": task_id,
            },
        )
        return self._validate_model_payload(AgentCandidateCommitResponse, response.data)

    def get_agent_candidate_commit(
        self,
        session_id: str,
        commit_id: str,
    ) -> AgentCandidateCommitResponse:
        """Get candidate persistence and worker-side backend apply state."""
        response = self._request(
            "GET",
            f"/agent-sessions/{session_id}/commits/{commit_id}",
        )
        return self._validate_model_payload(AgentCandidateCommitResponse, response.data)

    def apply_agent_candidate_commit(
        self,
        session_id: str,
        commit_id: str,
        *,
        idempotency_key: str,
        expected_state_version: int,
        push_to_github: bool = False,
    ) -> AgentCandidateCommitResponse:
        """Dispatch one committed candidate for worker-side backend application."""
        response = self._request(
            "POST",
            f"/agent-sessions/{session_id}/commits/{commit_id}/apply",
            json={
                "idempotency_key": idempotency_key,
                "expected_state_version": expected_state_version,
                "push_to_github": push_to_github,
            },
        )
        return self._validate_model_payload(AgentCandidateCommitResponse, response.data)

    def wait_for_agent_candidate_apply(
        self,
        session_id: str,
        commit_id: str,
        *,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 0.5,
    ) -> AgentCandidateCommitResponse:
        """Poll until backend application reaches applied or failed."""
        if timeout_seconds < 0 or poll_interval_seconds < 0:
            raise ValueError("Polling timeout and interval must be non-negative")
        deadline = time.monotonic() + timeout_seconds
        while True:
            commit = self.get_agent_candidate_commit(session_id, commit_id)
            if commit.backend_status in {"applied", "failed"}:
                return commit
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Agent candidate commit '{commit_id}' was not applied "
                    f"within {timeout_seconds} seconds"
                )
            self._sleep(poll_interval_seconds)

    def list_agent_actions(self, session_id: str) -> list[AgentActionResponse]:
        """List the audit trail for a local-agent session."""
        response = self._request("GET", f"/agent-sessions/{session_id}/actions")
        payload = self._validate_model_payload(AgentActionListResponse, response.data)
        return payload.items

    def list_tasks(self, *, backend: str | None = None) -> ListTaskResponse:
        response = self._request("GET", "/tasks", params=self._query_params(backend=backend))
        return self._validate_model_payload(ListTaskResponse, response.data)

    def get_task_result(self, task_id: str) -> TaskResultResponse:
        response = self._request("GET", f"/tasks/{task_id}/result")
        return self._validate_model_payload(TaskResultResponse, response.data)

    def list_task_knowledge(self) -> ListTaskKnowledgeResponse:
        response = self._request("GET", "/task-knowledge")
        return self._validate_model_payload(ListTaskKnowledgeResponse, response.data)

    def get_task_knowledge(self, task_name: str) -> TaskKnowledgeResponse:
        response = self._request("GET", f"/tasks/{task_name}/knowledge")
        return self._validate_model_payload(TaskKnowledgeResponse, response.data)

    def get_task_knowledge_markdown(self, task_name: str) -> str:
        response = self._request("GET", f"/tasks/{task_name}/knowledge/markdown")
        return response.data if isinstance(response.data, str) else ""

    def get_task_note(self, task_id: str) -> NoteModel:
        response = self._request("GET", f"/task-results/{task_id}/note")
        return self._validate_model_payload(NoteModel, response.data)

    def list_task_result_ai_reviews(
        self,
        *,
        chip_id: str | None = None,
        task_name: str | None = None,
        status: str | None = None,
        decision: str | None = None,
        latest_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> AiReviewListResponse:
        params = self._query_params(
            chip_id=chip_id,
            task_name=task_name,
            status=status,
            decision=decision,
            latest_only=latest_only,
            skip=skip,
            limit=limit,
        )
        response = self._request("GET", "/task-results/ai-review", params=params)
        return self._validate_model_payload(AiReviewListResponse, response.data)

    def list_task_result_ai_review_runs(
        self,
        *,
        chip_id: str | None = None,
        task_name: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> AiReviewRunListResponse:
        params = self._query_params(
            chip_id=chip_id,
            task_name=task_name,
            skip=skip,
            limit=limit,
        )
        response = self._request("GET", "/task-results/ai-review/runs", params=params)
        return self._validate_model_payload(AiReviewRunListResponse, response.data)

    def get_task_result_ai_review_run(self, review_run_id: str) -> AiReviewRunDetailResponse:
        response = self._request("GET", f"/task-results/ai-review/runs/{review_run_id}")
        return self._validate_model_payload(AiReviewRunDetailResponse, response.data)

    def cancel_execution(self, flow_run_id: str) -> CancelExecutionResponse:
        response = self._request("POST", f"/executions/{flow_run_id}/cancel", json={})
        return self._validate_model_payload(CancelExecutionResponse, response.data)

    def re_execute_execution(self, execution_id: str) -> ExecuteFlowResponse:
        response = self._request("POST", f"/executions/{execution_id}/re-execute", json={})
        return self._validate_model_payload(ExecuteFlowResponse, response.data)

    def upsert_task_note(self, task_id: str, *, content: str) -> NoteModel:
        response = self._request(
            "PUT",
            f"/task-results/{task_id}/note",
            json={"content": content},
        )
        return self._validate_model_payload(NoteModel, response.data)

    def delete_task_note(self, task_id: str) -> SuccessResponse:
        response = self._request("DELETE", f"/task-results/{task_id}/note", json={})
        return self._validate_model_payload(SuccessResponse, response.data)

    def set_task_result_excluded(
        self,
        task_id: str,
        *,
        excluded: bool,
        reason: str = "",
    ) -> TaskResultExcludeResponse:
        response = self._request(
            "POST",
            f"/task-results/{task_id}/exclude",
            json={"excluded": excluded, "reason": reason},
        )
        return self._validate_model_payload(TaskResultExcludeResponse, response.data)

    def re_execute_task_result(
        self,
        task_id: str,
        *,
        parameter_overrides: dict[str, dict[str, Any]] | None = None,
        update_params: bool = True,
        reconfigure: bool = False,
    ) -> ExecuteFlowResponse:
        body = BodyReExecuteTaskResult(
            parameter_overrides=parameter_overrides,
            update_params=update_params,
            reconfigure=reconfigure,
        )
        response = self._request(
            "POST",
            f"/task-results/{task_id}/re-execute",
            json=body.model_dump(mode="json"),
        )
        return self._validate_model_payload(ExecuteFlowResponse, response.data)

    def get_provenance_entity(self, entity_id: str) -> ParameterVersionResponse:
        response = self._request("GET", f"/provenance/entities/{entity_id}")
        return self._validate_model_payload(ParameterVersionResponse, response.data)

    def get_provenance_lineage(self, entity_id: str) -> LineageResponse:
        response = self._request("GET", f"/provenance/lineage/{entity_id}")
        return self._validate_model_payload(LineageResponse, response.data)

    def get_provenance_impact(self, entity_id: str) -> ImpactResponse:
        response = self._request("GET", f"/provenance/impact/{entity_id}")
        return self._validate_model_payload(ImpactResponse, response.data)

    def get_provenance_history(
        self,
        *,
        parameter_name: str,
        qid: str,
        limit: int = 50,
    ) -> ParameterHistoryResponse:
        response = self._request(
            "GET",
            "/provenance/history",
            params={"parameter_name": parameter_name, "qid": qid, "limit": limit},
        )
        return self._validate_model_payload(ParameterHistoryResponse, response.data)

    def get_provenance_stats(self) -> ProvenanceStatsResponse:
        response = self._request("GET", "/provenance/stats")
        return self._validate_model_payload(ProvenanceStatsResponse, response.data)

    def get_provenance_changes(
        self,
        *,
        parameter_names: list[str] | None = None,
        within_hours: int = 24,
        limit: int = 20,
    ) -> RecentChangesResponse:
        params = self._query_params(
            parameter_names=parameter_names,
            within_hours=within_hours,
            limit=limit,
        )
        response = self._request("GET", "/provenance/changes", params=params)
        return self._validate_model_payload(RecentChangesResponse, response.data)

    async def list_chips_async(self) -> ListChipsResponse:
        """Async variant of list_chips using the same auth/header behavior."""

        response = await self._request_async("/chips")
        return self._validate_model_payload(
            ListChipsResponse,
            response.json(),
        )

    async def get_task_results_timeseries_async(
        self,
        *,
        chip_id: str,
        parameter: str,
        tag: str | None = None,
        qid: str | None = None,
        start_at: str,
        end_at: str,
    ) -> TimeSeriesData:
        """Async variant of get_task_results_timeseries."""

        params: dict[str, Any] = {
            "chip_id": chip_id,
            "parameter": parameter,
            "start_at": start_at,
            "end_at": end_at,
        }
        if tag:
            params["tag"] = tag
        if qid:
            params["qid"] = qid

        response = await self._request_async("/task-results/timeseries", params=params)
        return self._validate_model_payload(
            TimeSeriesData,
            response.json(),
        )

    async def get_metrics_config_async(self) -> dict[str, Any]:
        """Async variant of get_metrics_config."""

        response = await self._request_async("/metrics/config")
        data = response.json()
        return data if isinstance(data, dict) else {}

    def normalize_chip_metrics(
        self, chip_id: str, payload: dict[str, Any]
    ) -> list[NormalizedMetricRecord]:
        records: list[NormalizedMetricRecord] = []

        metrics = payload.get("metrics")
        if isinstance(metrics, list):
            for item in metrics:
                record = self._normalize_row(chip_id, item)
                if record is not None:
                    records.append(record)

        qubit_metrics = payload.get("qubit_metrics")
        if isinstance(qubit_metrics, list):
            for item in qubit_metrics:
                qubit_id = str(item.get("qubit_id") or item.get("entity_id") or "")
                metric_map = item.get("metrics")
                if not qubit_id or not isinstance(metric_map, dict):
                    continue
                for metric_name, metric_payload in metric_map.items():
                    if not isinstance(metric_payload, dict):
                        continue
                    value = metric_payload.get("value")
                    if not isinstance(value, (int, float)):
                        continue
                    observed_at = self._parse_datetime(metric_payload.get("observed_at"))
                    records.append(
                        NormalizedMetricRecord(
                            chip_id=chip_id,
                            entity_type="qubit",
                            entity_id=qubit_id,
                            metric_name=str(metric_name),
                            value=float(value),
                            unit=str(metric_payload.get("unit") or ""),
                            observed_at=observed_at,
                        )
                    )

        coupling_metrics = payload.get("coupling_metrics")
        if isinstance(coupling_metrics, list):
            for item in coupling_metrics:
                record = self._normalize_row(chip_id, item, default_entity_type="coupling")
                if record is not None:
                    records.append(record)

        return records

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> RestApiResponse[Any]:
        attempts = self.config.retry.max_attempts

        for attempt in range(1, attempts + 1):
            headers = self._build_headers()
            try:
                response = self._rest_client.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers=headers,
                    raise_on_status=False,
                )
            except RestApiException as exc:
                if attempt < attempts:
                    self._sleep(self._retry_delay_for_attempt(attempt))
                    continue
                raise QDashTransportError(str(exc), payload=exc.body) from exc

            if (
                response.status_code == 401
                and self.config.api_token is None
                and self.config.username
            ):
                self._token = None
                if attempt < attempts:
                    self._sleep(self._retry_delay_for_attempt(attempt, response))
                    continue

            if response.status_code < 400:
                return response

            if self._is_retryable_status(response.status_code) and attempt < attempts:
                self._sleep(self._retry_delay_for_attempt(attempt, response))
                continue

            raise self._raise_for_api_response(method, path, response)

        raise QDashTransportError("request exhausted all retries")

    def _query_params(self, **params: Any) -> dict[str, Any]:
        return {key: value for key, value in params.items() if value is not None}

    async def _request_async(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        attempts = self.config.retry.max_attempts

        for attempt in range(1, attempts + 1):
            headers = self._build_headers()
            try:
                async with httpx.AsyncClient(
                    base_url=self.config.base_url,
                    timeout=self.config.timeout_sec,
                    verify=self.config.verify_tls,
                    proxy=self.config.proxy,
                ) as client:
                    response = await client.get(path, params=params, headers=headers)
            except httpx.HTTPError as exc:
                if attempt < attempts:
                    await asyncio.sleep(self._retry_delay_for_attempt(attempt))
                    continue
                raise QDashTransportError(str(exc)) from exc

            if (
                response.status_code == 401
                and self.config.api_token is None
                and self.config.username
            ):
                self._token = None
                if attempt < attempts:
                    await asyncio.sleep(self._retry_delay_for_attempt(attempt, response))
                    continue

            if response.status_code < 400:
                return response

            if self._is_retryable_status(response.status_code) and attempt < attempts:
                await asyncio.sleep(self._retry_delay_for_attempt(attempt, response))
                continue

            raise self._raise_for_response(response)

        raise QDashTransportError("request exhausted all retries")

    def _build_headers(self) -> dict[str, str]:
        token = self._get_token()
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": self.config.user_agent,
            "Authorization": f"Bearer {token}",
        }
        if self.config.project_id:
            headers["X-Project-Id"] = self.config.project_id
        if self.config.cf_access_client_id:
            headers["CF-Access-Client-Id"] = self.config.cf_access_client_id
        if self.config.cf_access_client_secret:
            headers["CF-Access-Client-Secret"] = self.config.cf_access_client_secret
        headers.update(self._default_headers)
        return headers

    def _get_token(self) -> str:
        if self._token:
            return self._token
        if self.config.api_token:
            self._token = self.config.api_token
            return self._token
        if not self.config.username:
            raise QDashAuthError("No authentication method configured", status_code=401)

        if not self.config.password_env:
            raise QDashAuthError(
                "password_env is required when using username/password", status_code=401
            )

        import os

        password = os.getenv(self.config.password_env)
        if not password:
            raise QDashAuthError(
                f"Missing password in env var {self.config.password_env}",
                status_code=401,
            )

        try:
            response = self._rest_client.request(
                "POST",
                "/auth/login",
                data={"username": self.config.username, "password": password},
                headers={"Accept": "application/json", "User-Agent": self.config.user_agent},
                raise_on_status=False,
            )
        except RestApiException as exc:
            raise QDashTransportError(str(exc), payload=exc.body) from exc
        if response.status_code >= 400:
            raise self._raise_for_api_response("POST", "/auth/login", response)

        payload = response.data
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise QDashAuthError("Login response did not include access_token", status_code=401)
        self._token = str(token)
        return self._token

    def _is_retryable_status(self, status_code: int) -> bool:
        # Follow OpenAPI-declared responses for the currently supported GET endpoints.
        # They do not define retryable status responses.
        return False

    def _retry_delay_for_attempt(
        self,
        attempt: int,
        response: httpx.Response | RestApiResponse[Any] | None = None,
    ) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass

        base = self.config.retry.base_delay_sec
        max_delay = self.config.retry.max_delay_sec
        delay = float(min(max_delay, base * (2 ** (attempt - 1))))
        jitter = random.uniform(0.0, delay * 0.1)  # noqa: S311
        return delay + jitter

    def _raise_for_response(self, response: httpx.Response) -> QDashApiError:
        status = response.status_code
        message = self._response_message(response)

        if status == 404:
            return QDashNotFoundError(message, status_code=status)
        if status == 422:
            return QDashValidationError(message, status_code=status)
        return QDashTransportError(message, status_code=status)

    def _raise_for_api_response(
        self,
        method: str,
        path: str,
        response: RestApiResponse[Any],
    ) -> QDashApiError:
        request = httpx.Request(method, f"{self.config.base_url}{path}")
        payload = response.data

        if isinstance(payload, (dict, list)):
            httpx_response = httpx.Response(
                response.status_code,
                request=request,
                json=payload,
                headers=response.headers,
            )
        else:
            httpx_response = httpx.Response(
                response.status_code,
                request=request,
                text="" if payload is None else str(payload),
                headers=response.headers,
            )

        err = self._raise_for_response(httpx_response)
        err.payload = payload
        return err

    def _response_message(self, response: httpx.Response) -> str:
        request = response.request
        endpoint = request.url.path if request is not None else "<unknown>"
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("detail")
                if detail:
                    return f"{response.status_code} {endpoint}: {detail}"
            if isinstance(body, str):
                return f"{response.status_code} {endpoint}: {body}"
        except Exception:  # noqa: S110
            pass
        return f"{response.status_code} {endpoint}"

    def _normalize_row(
        self,
        chip_id: str,
        row: Any,
        *,
        default_entity_type: str = "qubit",
    ) -> NormalizedMetricRecord | None:
        if not isinstance(row, dict):
            return None

        value = row.get("value")
        if not isinstance(value, (int, float)):
            return None

        entity_id = row.get("entity_id") or row.get("qubit_id") or row.get("coupling_id")
        metric_name = row.get("metric_name")
        if not entity_id or not metric_name:
            return None

        return NormalizedMetricRecord(
            chip_id=chip_id,
            entity_type=str(row.get("entity_type") or default_entity_type),
            entity_id=str(entity_id),
            metric_name=str(metric_name),
            value=float(value),
            unit=str(row.get("unit") or ""),
            observed_at=self._parse_datetime(row.get("observed_at")),
        )

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC)
        except ValueError:
            return None
