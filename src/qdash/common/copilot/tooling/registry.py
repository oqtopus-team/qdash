"""Tool executor registry for Copilot data-loading helpers."""

from __future__ import annotations

from typing import Any, Protocol


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

    def build_tool_executors(self) -> dict[str, Any]:
        """Build the tool executor mapping for LLM function calling."""
        from qdash.common.copilot.sandbox import execute_python_analysis

        return (
            self._build_qubit_analysis_tool_executors()
            | self._build_chip_overview_tool_executors()
            | self._build_history_and_provenance_tool_executors()
            | {"execute_python_analysis": lambda args: execute_python_analysis(args["code"])}
        )

    def _build_qubit_analysis_tool_executors(self) -> dict[str, Any]:
        """Build tool executors for task-result and qubit-level analysis lookups."""
        return {
            "get_qubit_params": lambda args: self._service.load_qubit_params(
                args["chip_id"], args["qid"]
            ),
            "get_latest_task_result": lambda args: self._service.load_latest_task_result(
                args["task_name"], args["chip_id"], args["qid"]
            ),
            "get_task_history": lambda args: self._service.load_task_history(
                args["task_name"], args["chip_id"], args["qid"], args.get("last_n", 5)
            ),
            "get_parameter_timeseries": lambda args: self._service.load_parameter_timeseries(
                args["parameter_name"], args["chip_id"], args["qid"], args.get("last_n", 10)
            ),
            "compare_qubits": lambda args: self._service.load_compare_qubits(
                args["chip_id"], args["qids"], args.get("param_names")
            ),
            "get_coupling_params": lambda args: self._service.load_coupling_params_tool(
                args["chip_id"],
                args.get("coupling_id"),
                args.get("qubit_id"),
                args.get("param_names"),
            ),
        }

    def _build_chip_overview_tool_executors(self) -> dict[str, Any]:
        """Build tool executors for chip summaries, topology, and metric overviews."""
        return {
            "get_chip_summary": lambda args: self._service.load_chip_summary(
                args["chip_id"], args.get("param_names")
            ),
            "get_chip_topology": lambda args: self._service.load_chip_topology(args["chip_id"]),
            "generate_chip_heatmap": lambda args: self._service.load_chip_heatmap(
                args["chip_id"],
                args["metric_name"],
                args.get("selection_mode", "latest"),
                args.get("within_hours"),
            ),
            "list_available_parameters": lambda args: self._service.load_available_parameters(
                args["chip_id"], args.get("qid")
            ),
            "get_chip_parameter_timeseries": lambda args: self._service.load_chip_parameter_timeseries(
                args["parameter_name"],
                args["chip_id"],
                args.get("last_n", 10),
                args.get("qids"),
            ),
        }

    def _build_history_and_provenance_tool_executors(self) -> dict[str, Any]:
        """Build tool executors for execution history, notes, and provenance lookups."""
        return {
            "get_execution_history": lambda args: self._service.load_execution_history(
                args["chip_id"], args.get("status"), args.get("tags"), args.get("last_n", 10)
            ),
            "search_task_results": lambda args: self._service.load_search_task_results(
                args["chip_id"],
                args.get("task_name"),
                args.get("qid"),
                args.get("status"),
                args.get("execution_id"),
                args.get("last_n", 10),
            ),
            "get_calibration_notes": lambda args: self._service.load_calibration_notes(
                args["chip_id"],
                args.get("execution_id"),
                args.get("task_id"),
                args.get("last_n", 10),
            ),
            "get_parameter_lineage": lambda args: self._service.load_parameter_lineage(
                args["parameter_name"], args["qid"], args["chip_id"], args.get("last_n", 10)
            ),
            "get_provenance_lineage_graph": lambda args: self._service.load_provenance_lineage_graph(
                args["entity_id"], args["chip_id"], args.get("max_depth", 5)
            ),
        }
