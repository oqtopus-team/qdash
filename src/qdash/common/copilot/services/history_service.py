"""Historical task, execution, and lineage loaders for Copilot data access."""

from __future__ import annotations

from typing import Any, Protocol


class CopilotHistoryDataAccessProtocol(Protocol):
    """Subset of data-access methods used for historical Copilot views."""

    def load_completed_task_history(
        self,
        task_name: str,
        chip_id: str,
        qid: str,
        last_n: int,
    ) -> list[Any]: ...

    def load_parameter_timeseries_docs(
        self,
        parameter_name: str,
        chip_id: str,
        qid: str,
        last_n: int,
    ) -> list[Any]: ...

    def load_execution_history_docs(
        self,
        chip_id: str,
        status: str | None,
        tags: list[str] | None,
        last_n: int,
    ) -> list[Any]: ...

    def load_task_results(
        self,
        chip_id: str,
        task_name: str | None,
        qid: str | None,
        status: str | None,
        execution_id: str | None,
        last_n: int,
    ) -> list[Any]: ...

    def load_calibration_notes(
        self,
        chip_id: str,
        execution_id: str | None,
        task_id: str | None,
        last_n: int,
    ) -> list[Any]: ...

    def load_parameter_versions(
        self,
        parameter_name: str,
        qid: str,
        chip_id: str,
        last_n: int,
    ) -> list[Any]: ...


class CopilotHistoryLoader:
    """Load history-oriented Copilot payloads from normalized data access."""

    def __init__(
        self,
        *,
        data_access: CopilotHistoryDataAccessProtocol,
        compact_number: Any,
        compact_timestamp: Any,
        compact_output_parameters: Any,
    ) -> None:
        self._data_access = data_access
        self._compact_number = compact_number
        self._compact_timestamp = compact_timestamp
        self._compact_output_parameters = compact_output_parameters

    def load_task_history(
        self,
        *,
        task_name: str,
        chip_id: str,
        qid: str,
        last_n: int = 5,
    ) -> list[dict[str, Any]]:
        """Load recent completed results for the same task+qubit."""
        docs = self._data_access.load_completed_task_history(task_name, chip_id, qid, last_n)
        return [
            {
                "output_parameters": self._compact_output_parameters(doc.output_parameters or {}),
                "start_at": self._compact_timestamp(doc.start_at.isoformat() if doc.start_at else None),
                "execution_id": doc.execution_id,
            }
            for doc in docs
        ]

    def load_latest_task_result(
        self,
        *,
        task_name: str,
        chip_id: str,
        qid: str,
    ) -> dict[str, Any]:
        """Load the latest completed result for a task+qubit."""
        results = self.load_task_history(task_name=task_name, chip_id=chip_id, qid=qid, last_n=1)
        return results[0] if results else {"error": "No results found"}

    def load_parameter_timeseries(
        self,
        *,
        parameter_name: str,
        chip_id: str,
        qid: str,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Load time series data for a specific output parameter by name."""
        docs = self._data_access.load_parameter_timeseries_docs(
            parameter_name,
            chip_id,
            qid,
            last_n,
        )

        results: list[dict[str, Any]] = []
        for doc in reversed(docs):
            param_data = (doc.output_parameters or {}).get(parameter_name)
            if param_data is None:
                continue
            entry: dict[str, Any] = {
                "start_at": doc.start_at.isoformat() if doc.start_at else None,
                "execution_id": doc.execution_id,
                "task_name": doc.name,
            }
            if isinstance(param_data, dict):
                entry["value"] = param_data.get("value")
                entry["unit"] = param_data.get("unit", "")
                entry["calibrated_at"] = param_data.get("calibrated_at")
            else:
                entry["value"] = param_data
                entry["unit"] = ""
            results.append(entry)

        if not results:
            return [{"error": f"No results found for parameter '{parameter_name}' on qid={qid}"}]
        return results

    def load_execution_history(
        self,
        *,
        chip_id: str,
        status: str | None = None,
        tags: list[str] | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Load recent execution history for a chip."""
        docs = self._data_access.load_execution_history_docs(chip_id, status, tags, last_n)
        results = [
            {
                "execution_id": doc.execution_id,
                "name": doc.name,
                "status": doc.status,
                "chip_id": doc.chip_id,
                "tags": doc.tags,
                "start_at": self._compact_timestamp(doc.start_at.isoformat() if doc.start_at else None),
                "end_at": self._compact_timestamp(doc.end_at.isoformat() if doc.end_at else None),
                "elapsed_time": self._compact_number(doc.elapsed_time),
                "message": doc.message,
            }
            for doc in docs
        ]
        if not results:
            return [{"error": f"No executions found for chip_id={chip_id}"}]
        return results

    def load_search_task_results(
        self,
        *,
        chip_id: str,
        task_name: str | None = None,
        qid: str | None = None,
        status: str | None = None,
        execution_id: str | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Search task result history with flexible filters."""
        docs = self._data_access.load_task_results(
            chip_id,
            task_name,
            qid,
            status,
            execution_id,
            last_n,
        )
        results = [
            {
                "task_id": doc.task_id,
                "task_name": doc.name,
                "qid": doc.qid,
                "status": doc.status,
                "execution_id": doc.execution_id,
                "start_at": self._compact_timestamp(doc.start_at.isoformat() if doc.start_at else None),
                "end_at": self._compact_timestamp(doc.end_at.isoformat() if doc.end_at else None),
                "elapsed_time": self._compact_number(doc.elapsed_time),
                "output_parameters": self._compact_output_parameters(doc.output_parameters or {}),
                "message": doc.message,
            }
            for doc in docs
        ]
        if not results:
            return [{"error": "No task results found matching the filters"}]
        return results

    def load_calibration_notes(
        self,
        *,
        chip_id: str,
        execution_id: str | None = None,
        task_id: str | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Load calibration notes for a chip."""
        docs = self._data_access.load_calibration_notes(chip_id, execution_id, task_id, last_n)
        results = [
            {
                "execution_id": doc.execution_id,
                "task_id": doc.task_id,
                "note": doc.note,
                "timestamp": doc.timestamp.isoformat() if doc.timestamp else None,
            }
            for doc in docs
        ]
        if not results:
            return [{"error": f"No calibration notes found for chip_id={chip_id}"}]
        return results

    def load_parameter_lineage(
        self,
        *,
        parameter_name: str,
        qid: str,
        chip_id: str,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Load version history for a specific parameter."""
        docs = self._data_access.load_parameter_versions(parameter_name, qid, chip_id, last_n)
        results = [
            {
                "version": doc.version,
                "value": self._compact_number(doc.value),
                "unit": doc.unit,
                "error": self._compact_number(doc.error) if doc.error else None,
                "execution_id": doc.execution_id,
                "task_id": doc.task_id,
                "task_name": doc.task_name,
                "valid_from": self._compact_timestamp(
                    doc.valid_from.isoformat() if doc.valid_from else None
                ),
                "valid_until": self._compact_timestamp(
                    doc.valid_until.isoformat() if doc.valid_until else None
                ),
            }
            for doc in docs
        ]
        if not results:
            return [
                {
                    "error": (
                        f"No version history found for parameter '{parameter_name}' "
                        f"on qid={qid}, chip_id={chip_id}"
                    )
                }
            ]
        return results
