"""Shared Copilot runtime entrypoint.

This module is the main navigation point for the Copilot package.

- ``runtime.py`` wires together the package-level components and exposes
  the public methods used by the API and workflow layers.
- ``services/`` contains the feature-oriented loading and transformation logic.
- ``formatters/`` contains LLM-facing compaction and presentation helpers.
- ``tooling/`` contains tool-registry assembly for agent function calling.

When reading the package, start here to see the high-level composition,
then jump into ``services/`` for the actual behavior.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qdash.common.copilot.formatters.compact import (
    compact_number as _compact_number,
)
from qdash.common.copilot.formatters.compact import (
    compact_output_parameters as _compact_output_parameters,
)
from qdash.common.copilot.formatters.compact import (
    compact_timestamp as _compact_timestamp,
)
from qdash.common.copilot.services.analysis_context_service import AnalysisContextBuilder
from qdash.common.copilot.services.chip_overview_service import ChipOverviewLoader
from qdash.common.copilot.services.data_access import CopilotDataAccess
from qdash.common.copilot.services.heatmap_service import ChipHeatmapLoader
from qdash.common.copilot.services.history_service import CopilotHistoryLoader
from qdash.common.copilot.services.provenance_context_service import (
    ProvenanceLineageGraphLoader,
    ProvenanceServiceProtocol,
)
from qdash.common.copilot.services.support_service import CopilotSupportService
from qdash.common.copilot.services.topology_context_service import TopologyContextLoader
from qdash.common.copilot.tooling.registry import ToolExecutorRegistryBuilder
from qdash.common.utils.json import sanitize_for_json

if TYPE_CHECKING:
    from qdash.common.copilot.config import CopilotConfig
    from qdash.common.copilot.contracts import AnalysisContextResult

logger = logging.getLogger(__name__)

MAX_FIGURE_SIZE = 5 * 1024 * 1024  # 5MB
FALLBACK_QUERY_LIMIT = 500  # Max documents to scan for manual aggregation fallback


class CopilotRuntime:
    """Runtime entrypoint that composes shared Copilot services.

    This class intentionally stays thin: it wires together data access,
    service modules, and tool registration, then exposes a stable surface
    for API routes and workflow tasks.
    """

    def __init__(self, data_access: CopilotDataAccess | None = None) -> None:
        self._data_access = data_access or CopilotDataAccess(FALLBACK_QUERY_LIMIT)
        self._support_service = CopilotSupportService(
            data_access=self._data_access,
            logger=logger,
            max_figure_size=MAX_FIGURE_SIZE,
        )
        self._analysis_context_builder = AnalysisContextBuilder(
            load_qubit_params=self._analysis_load_qubit_params,
            load_task_result=self._analysis_load_task_result,
            load_task_history=self._analysis_load_task_history,
            load_neighbor_qubit_params=self._analysis_load_neighbor_qubit_params,
            load_coupling_params=self._analysis_load_coupling_params,
            load_figure_as_base64=self._analysis_load_figure_as_base64,
            collect_expected_images=self._analysis_collect_expected_images,
        )
        self._heatmap_loader = ChipHeatmapLoader(
            data_access=self._data_access,
            compact_number=_compact_number,
        )
        self._chip_overview_loader = ChipOverviewLoader(
            data_access=self._data_access,
            compact_number=_compact_number,
        )
        self._history_loader = CopilotHistoryLoader(
            data_access=self._data_access,
            compact_number=_compact_number,
            compact_timestamp=_compact_timestamp,
            compact_output_parameters=_compact_output_parameters,
        )
        self._topology_context_loader = TopologyContextLoader(
            data_access=self._data_access,
            compact_number=_compact_number,
            sanitize_for_json=sanitize_for_json,
        )
        self._provenance_lineage_graph_loader = ProvenanceLineageGraphLoader(
            resolve_project_id=self._provenance_resolve_project_id,
            get_provenance_service=self._provenance_get_provenance_service,
            compact_number=_compact_number,
            compact_timestamp=_compact_timestamp,
        )
        self._tool_executor_registry_builder = ToolExecutorRegistryBuilder(self)

    def _analysis_load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]:
        """Forward qubit-param lookup for analysis context assembly."""
        return self.load_qubit_params(chip_id, qid)

    def _analysis_load_task_result(self, task_id: str) -> dict[str, Any] | None:
        """Forward task-result lookup for analysis context assembly."""
        return self.load_task_result(task_id)

    def _analysis_load_task_history(
        self,
        task_name: str,
        chip_id: str,
        qid: str,
        last_n: int,
    ) -> list[dict[str, Any]]:
        """Forward task-history lookup for analysis context assembly."""
        return self.load_task_history(task_name, chip_id, qid, last_n)

    def _analysis_load_neighbor_qubit_params(
        self,
        chip_id: str,
        qid: str,
        params: list[str] | None,
    ) -> dict[str, dict[str, Any]]:
        """Forward neighbor-qubit lookup for analysis context assembly."""
        return self.load_neighbor_qubit_params(chip_id, qid, params or [])

    def _analysis_load_coupling_params(
        self,
        chip_id: str,
        qid: str,
        params: list[str] | None,
    ) -> dict[str, dict[str, Any]]:
        """Forward coupling lookup for analysis context assembly."""
        return self.load_coupling_params(chip_id, qid, params or [])

    def _analysis_load_figure_as_base64(self, figure_paths: list[str]) -> str | None:
        """Forward figure loading for analysis context assembly."""
        return self.load_figure_as_base64(figure_paths)

    def _analysis_collect_expected_images(
        self,
        knowledge: Any,
        max_images: int | None,
    ) -> list[tuple[str, str]]:
        """Forward expected-image lookup for analysis context assembly."""
        return self.collect_expected_images(knowledge, max_images=max_images)

    def _provenance_resolve_project_id(self, chip_id: str) -> str | None:
        """Forward project-id lookup for provenance lineage assembly."""
        return self._resolve_project_id(chip_id)

    def _provenance_get_provenance_service(self) -> ProvenanceServiceProtocol:
        """Forward provenance-service lookup for lineage assembly."""
        return self._get_provenance_service()

    def load_default_chip_id(self) -> str | None:
        """Load the most recently installed chip_id from DB."""
        return self._support_service.load_default_chip_id()

    def load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]:
        """Load current qubit parameters from DB."""
        return self._support_service.load_qubit_params(chip_id, qid)

    def load_task_result(self, task_id: str) -> dict[str, Any] | None:
        """Load task result from DB."""
        return self._support_service.load_task_result(task_id)

    def load_figure_as_base64(self, figure_paths: list[str]) -> str | None:
        """Read the first existing PNG file from figure_paths and return base64."""
        return self._support_service.load_figure_as_base64(figure_paths)

    def collect_expected_images(
        self,
        knowledge: Any,
        max_images: int | None = None,
    ) -> list[tuple[str, str]]:
        """Collect expected reference images from TaskKnowledge.

        Returns list of (base64_data, alt_text) for images with embedded data.
        Includes both task-level images and case-level images.
        """
        return self._support_service.collect_expected_images(knowledge, max_images=max_images)

    def load_task_history(
        self, task_name: str, chip_id: str, qid: str, last_n: int = 5
    ) -> list[dict[str, Any]]:
        """Load recent completed results for the same task+qubit."""
        return self._history_loader.load_task_history(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
            last_n=last_n,
        )

    def load_neighbor_qubit_params(
        self, chip_id: str, qid: str, param_names: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Load specified parameters from neighboring qubits via topology."""
        return self._topology_context_loader.load_neighbor_qubit_params(
            chip_id=chip_id,
            qid=qid,
            param_names=param_names,
        )

    def load_coupling_params(
        self, chip_id: str, qid: str, param_names: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Load specified parameters from couplings related to the target qubit."""
        return self._topology_context_loader.load_coupling_params(
            chip_id=chip_id,
            qid=qid,
            param_names=param_names,
        )

    def load_latest_task_result(self, task_name: str, chip_id: str, qid: str) -> dict[str, Any]:
        """Load the latest completed result for a task+qubit."""
        return self._history_loader.load_latest_task_result(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
        )

    def load_parameter_timeseries(
        self, parameter_name: str, chip_id: str, qid: str, last_n: int = 10
    ) -> list[dict[str, Any]]:
        """Load time series data for a specific output parameter by name.

        Queries task_result_history by output_parameter_names field,
        which is indexed and allows parameter-name-based lookups
        regardless of task name.
        """
        return self._history_loader.load_parameter_timeseries(
            parameter_name=parameter_name,
            chip_id=chip_id,
            qid=qid,
            last_n=last_n,
        )

    def load_chip_parameter_timeseries(
        self,
        parameter_name: str,
        chip_id: str,
        last_n: int = 10,
        qids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Load per-qubit timeseries and summary for a parameter.

        Single DB query replaces N individual get_parameter_timeseries calls.
        Returns per-qubit timeseries (value + timestamp), stats, trend,
        and chip-wide statistics — enough data for charts and tables.

        Parameters
        ----------
        qids : list[str] | None
            Optional list of qubit IDs to fetch. If None, fetches all qubits.
        """
        return self._chip_overview_loader.load_chip_parameter_timeseries(
            parameter_name=parameter_name,
            chip_id=chip_id,
            last_n=last_n,
            qids=qids,
        )

    def load_chip_summary(
        self, chip_id: str, param_names: list[str] | None = None
    ) -> dict[str, Any]:
        """Load summary of all qubits on a chip with computed statistics.

        Returns statistics (always included) and a list-of-dicts ``qubits``
        table.
        """
        return self._chip_overview_loader.load_chip_summary(
            chip_id=chip_id,
            param_names=param_names,
        )

    def load_coupling_params_tool(
        self,
        chip_id: str,
        coupling_id: str | None = None,
        qubit_id: str | None = None,
        param_names: list[str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Load coupling parameters by coupling_id or qubit_id."""
        return self._topology_context_loader.load_coupling_params_tool(
            chip_id=chip_id,
            coupling_id=coupling_id,
            qubit_id=qubit_id,
            param_names=param_names,
        )

    def load_execution_history(
        self,
        chip_id: str,
        status: str | None = None,
        tags: list[str] | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Load recent execution history for a chip."""
        return self._history_loader.load_execution_history(
            chip_id=chip_id,
            status=status,
            tags=tags,
            last_n=last_n,
        )

    def load_compare_qubits(
        self, chip_id: str, qids: list[str], param_names: list[str] | None = None
    ) -> dict[str, Any]:
        """Load and compare parameters across multiple qubits.

        Returns compact {qid: {param: value}} with values only (no unit/description).
        """
        return self._topology_context_loader.load_compare_qubits(
            chip_id=chip_id,
            qids=qids,
            param_names=param_names,
        )

    def load_chip_topology(self, chip_id: str) -> dict[str, Any]:
        """Load chip topology information."""
        return self._topology_context_loader.load_chip_topology(chip_id=chip_id)

    def load_search_task_results(
        self,
        chip_id: str,
        task_name: str | None = None,
        qid: str | None = None,
        status: str | None = None,
        execution_id: str | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Search task result history with flexible filters."""
        return self._history_loader.load_search_task_results(
            chip_id=chip_id,
            task_name=task_name,
            qid=qid,
            status=status,
            execution_id=execution_id,
            last_n=last_n,
        )

    def load_calibration_notes(
        self,
        chip_id: str,
        execution_id: str | None = None,
        task_id: str | None = None,
        last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Load calibration notes for a chip."""
        return self._history_loader.load_calibration_notes(
            chip_id=chip_id,
            execution_id=execution_id,
            task_id=task_id,
            last_n=last_n,
        )

    def _resolve_project_id(self, chip_id: str) -> str | None:
        """Resolve project_id from chip_id via ChipDocument."""
        doc = self._data_access.load_chip(chip_id)
        if doc is None:
            return None
        return str(doc.project_id)

    def _get_provenance_service(self) -> ProvenanceServiceProtocol:
        """Build a lightweight provenance adapter for lineage lookups."""
        return self._data_access.build_provenance_service()

    def load_provenance_lineage_graph(
        self, entity_id: str, chip_id: str, max_depth: int = 5
    ) -> dict[str, Any]:
        """Load the provenance lineage graph and return an LLM-friendly summary."""
        return self._provenance_lineage_graph_loader.load_provenance_lineage_graph(
            entity_id=entity_id,
            chip_id=chip_id,
            max_depth=max_depth,
        )

    def load_parameter_lineage(
        self, parameter_name: str, qid: str, chip_id: str, last_n: int = 10
    ) -> list[dict[str, Any]]:
        """Load version history for a specific parameter."""
        return self._history_loader.load_parameter_lineage(
            parameter_name=parameter_name,
            qid=qid,
            chip_id=chip_id,
            last_n=last_n,
        )

    def load_chip_heatmap(
        self,
        chip_id: str,
        metric_name: str,
        selection_mode: str = "latest",
        within_hours: int | None = None,
    ) -> dict[str, Any]:
        """Generate a chip-wide heatmap for a qubit metric.

        Returns a Plotly figure dict suitable for the chat UI.
        """
        return self._heatmap_loader.load_chip_heatmap(
            chip_id=chip_id,
            metric_name=metric_name,
            selection_mode=selection_mode,
            within_hours=within_hours,
        )

    def load_available_parameters(
        self,
        chip_id: str,
        qid: str | None = None,
    ) -> dict[str, Any]:
        """List distinct output parameter names recorded for a chip."""
        return self._support_service.load_available_parameters(chip_id, qid=qid)

    def build_analysis_context(
        self,
        task_name: str,
        chip_id: str,
        qid: str,
        task_id: str,
        image_base64: str | None,
        config: CopilotConfig,
    ) -> AnalysisContextResult:
        """Build a full analysis context from DB data and TaskKnowledge.

        Consolidates the duplicated context-building logic that was
        previously inlined in both ``analyze_task_result`` and
        ``analyze_task_result_stream``.
        """
        return self._analysis_context_builder.build_analysis_context(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
            task_id=task_id,
            image_base64=image_base64,
            config=config,
        )

    @staticmethod
    def build_images_sent_metadata(
        image_base64: str | None,
        figure_paths: list[str],
        expected_images: list[tuple[str, str]],
        task_name: str,
    ) -> dict[str, Any]:
        """Build the ``images_sent`` metadata dict for analysis responses."""
        return CopilotSupportService.build_images_sent_metadata(
            image_base64=image_base64,
            figure_paths=figure_paths,
            expected_images=expected_images,
            task_name=task_name,
        )

    def build_tool_executors(self) -> dict[str, Any]:
        """Build the tool executor mapping for LLM function calling.

        Note: ``execute_python_analysis`` is overridden by ``_wrap_tool_executors``
        in ``llm_agent.py`` to auto-inject the data_store.
        """
        return self._tool_executor_registry_builder.build_tool_executors()
