"""Tool executor registry for Copilot data-loading helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from qdash.copilot.tooling.models import (
    CompareQubitsArgs,
    ExecutePythonAnalysisArgs,
    GenerateChipHeatmapArgs,
    GetCalibrationNotesArgs,
    GetChipParameterTimeseriesArgs,
    GetChipSummaryArgs,
    GetChipTopologyArgs,
    GetCouplingParamsArgs,
    GetExecutionHistoryArgs,
    GetLatestTaskResultArgs,
    GetParameterLineageArgs,
    GetParameterTimeseriesArgs,
    GetProvenanceLineageGraphArgs,
    GetQubitParamsArgs,
    GetTaskHistoryArgs,
    ListAvailableParametersArgs,
    SearchTaskResultsArgs,
)

ToolExecutor = Callable[[dict[str, Any]], Any]
ToolExecutors = dict[str, ToolExecutor]
_ToolArgsModel = TypeVar("_ToolArgsModel", bound=BaseModel)


class ToolRegistryDataService(Protocol):
    """Minimal service surface needed to build Copilot tool executors."""

    def load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]: ...

    def load_latest_task_result(self, task_name: str, chip_id: str, qid: str) -> dict[str, Any]: ...

    def load_task_history(
        self,
        task_name: str,
        chip_id: str,
        qid: str,
        last_n: int = 5,
    ) -> list[dict[str, Any]]: ...

    def load_parameter_timeseries(
        self,
        parameter_name: str,
        chip_id: str,
        qid: str,
        last_n: int = 10,
    ) -> list[dict[str, Any]]: ...

    def load_chip_summary(
        self,
        chip_id: str,
        param_names: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def load_coupling_params_tool(
        self,
        chip_id: str,
        coupling_id: str | None = None,
        qubit_id: str | None = None,
        param_names: list[str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]: ...

    def load_execution_history(
        self,
        chip_id: str,
        status: str | None = None,
        tags: list[str] | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]: ...

    def load_compare_qubits(
        self,
        chip_id: str,
        qids: list[str],
        param_names: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def load_chip_topology(self, chip_id: str) -> dict[str, Any]: ...

    def load_search_task_results(
        self,
        chip_id: str,
        task_name: str | None = None,
        qid: str | None = None,
        status: str | None = None,
        execution_id: str | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]: ...

    def load_calibration_notes(
        self,
        chip_id: str,
        execution_id: str | None = None,
        task_id: str | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]: ...

    def load_parameter_lineage(
        self,
        parameter_name: str,
        qid: str,
        chip_id: str,
        last_n: int = 10,
    ) -> list[dict[str, Any]]: ...

    def load_provenance_lineage_graph(
        self,
        entity_id: str,
        chip_id: str,
        max_depth: int = 5,
    ) -> dict[str, Any]: ...

    def load_chip_heatmap(
        self,
        chip_id: str,
        metric_name: str,
        selection_mode: str = "latest",
        within_hours: int | None = None,
    ) -> dict[str, Any]: ...

    def load_available_parameters(
        self,
        chip_id: str,
        qid: str | None = None,
    ) -> dict[str, Any]: ...

    def load_chip_parameter_timeseries(
        self,
        parameter_name: str,
        chip_id: str,
        last_n: int = 10,
        qids: list[str] | None = None,
    ) -> dict[str, Any]: ...


class ToolExecutorRegistryBuilder:
    """Build the tool executor mapping for Copilot function calling."""

    def __init__(self, service: ToolRegistryDataService) -> None:
        self._service = service

    @staticmethod
    def _build_executor(
        args_model: type[_ToolArgsModel],
        handler: Callable[[_ToolArgsModel], Any],
    ) -> ToolExecutor:
        """Wrap a handler with explicit Pydantic validation for tool-call arguments."""
        return lambda args: handler(args_model.model_validate(args))

    def build_tool_executors(self) -> ToolExecutors:
        """Build the tool executor mapping for LLM function calling."""
        from qdash.copilot.tooling.sandbox import execute_python_analysis

        return (
            self._build_qubit_analysis_tool_executors()
            | self._build_chip_overview_tool_executors()
            | self._build_history_and_provenance_tool_executors()
            | {
                "execute_python_analysis": self._build_executor(
                    ExecutePythonAnalysisArgs,
                    lambda args: execute_python_analysis(args.code),
                )
            }
        )

    def _build_qubit_analysis_tool_executors(self) -> ToolExecutors:
        """Build tool executors for task-result and qubit-level analysis lookups."""
        return {
            "get_qubit_params": self._build_executor(
                GetQubitParamsArgs,
                lambda args: self._service.load_qubit_params(args.chip_id, args.qid),
            ),
            "get_latest_task_result": self._build_executor(
                GetLatestTaskResultArgs,
                lambda args: self._service.load_latest_task_result(
                    args.task_name, args.chip_id, args.qid
                ),
            ),
            "get_task_history": self._build_executor(
                GetTaskHistoryArgs,
                lambda args: self._service.load_task_history(
                    args.task_name, args.chip_id, args.qid, args.last_n
                ),
            ),
            "get_parameter_timeseries": self._build_executor(
                GetParameterTimeseriesArgs,
                lambda args: self._service.load_parameter_timeseries(
                    args.parameter_name, args.chip_id, args.qid, args.last_n
                ),
            ),
            "compare_qubits": self._build_executor(
                CompareQubitsArgs,
                lambda args: self._service.load_compare_qubits(
                    args.chip_id, args.qids, args.param_names
                ),
            ),
            "get_coupling_params": self._build_executor(
                GetCouplingParamsArgs,
                lambda args: self._service.load_coupling_params_tool(
                    args.chip_id,
                    args.coupling_id,
                    args.qubit_id,
                    args.param_names,
                ),
            ),
        }

    def _build_chip_overview_tool_executors(self) -> ToolExecutors:
        """Build tool executors for chip summaries, topology, and metric overviews."""
        return {
            "get_chip_summary": self._build_executor(
                GetChipSummaryArgs,
                lambda args: self._service.load_chip_summary(args.chip_id, args.param_names),
            ),
            "get_chip_topology": self._build_executor(
                GetChipTopologyArgs,
                lambda args: self._service.load_chip_topology(args.chip_id),
            ),
            "generate_chip_heatmap": self._build_executor(
                GenerateChipHeatmapArgs,
                lambda args: self._service.load_chip_heatmap(
                    args.chip_id,
                    args.metric_name,
                    args.selection_mode,
                    args.within_hours,
                ),
            ),
            "list_available_parameters": self._build_executor(
                ListAvailableParametersArgs,
                lambda args: self._service.load_available_parameters(args.chip_id, args.qid),
            ),
            "get_chip_parameter_timeseries": self._build_executor(
                GetChipParameterTimeseriesArgs,
                lambda args: self._service.load_chip_parameter_timeseries(
                    args.parameter_name,
                    args.chip_id,
                    args.last_n,
                    args.qids,
                ),
            ),
        }

    def _build_history_and_provenance_tool_executors(self) -> ToolExecutors:
        """Build tool executors for execution history, notes, and provenance lookups."""
        return {
            "get_execution_history": self._build_executor(
                GetExecutionHistoryArgs,
                lambda args: self._service.load_execution_history(
                    args.chip_id, args.status, args.tags, args.last_n
                ),
            ),
            "search_task_results": self._build_executor(
                SearchTaskResultsArgs,
                lambda args: self._service.load_search_task_results(
                    args.chip_id,
                    args.task_name,
                    args.qid,
                    args.status,
                    args.execution_id,
                    args.last_n,
                ),
            ),
            "get_calibration_notes": self._build_executor(
                GetCalibrationNotesArgs,
                lambda args: self._service.load_calibration_notes(
                    args.chip_id,
                    args.execution_id,
                    args.task_id,
                    args.last_n,
                ),
            ),
            "get_parameter_lineage": self._build_executor(
                GetParameterLineageArgs,
                lambda args: self._service.load_parameter_lineage(
                    args.parameter_name, args.qid, args.chip_id, args.last_n
                ),
            ),
            "get_provenance_lineage_graph": self._build_executor(
                GetProvenanceLineageGraphArgs,
                lambda args: self._service.load_provenance_lineage_graph(
                    args.entity_id, args.chip_id, args.max_depth
                ),
            ),
        }
