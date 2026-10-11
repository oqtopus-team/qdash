"""Data loading for a chat about one task result.

The Pi Agent Runtime answers chats with pi-qdash's tools; the API's only
model-facing job is to open a task chat with the result's context and
figures. This runtime composes the loaders that build that context.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qdash.common.utils.json import sanitize_for_json
from qdash.copilot.formatters.compact import (
    compact_number as _compact_number,
)
from qdash.copilot.formatters.compact import (
    compact_output_parameters as _compact_output_parameters,
)
from qdash.copilot.formatters.compact import (
    compact_timestamp as _compact_timestamp,
)
from qdash.copilot.services.data_access import CopilotDataAccess
from qdash.copilot.services.history_service import CopilotHistoryLoader
from qdash.copilot.services.support_service import CopilotSupportService
from qdash.copilot.services.task_context_service import TaskContextBuilder
from qdash.copilot.services.topology_context_service import TopologyContextLoader

if TYPE_CHECKING:
    from qdash.copilot.config import CopilotConfig
    from qdash.copilot.contracts import TaskContextBundle

logger = logging.getLogger(__name__)

MAX_FIGURE_SIZE = 5 * 1024 * 1024  # 5MB
FALLBACK_QUERY_LIMIT = 500  # Max documents to scan for manual aggregation fallback


class CopilotRuntime:
    """Composes the loaders behind a task result's chat context."""

    def __init__(self, data_access: CopilotDataAccess | None = None) -> None:
        self._data_access = data_access or CopilotDataAccess(FALLBACK_QUERY_LIMIT)
        self._support_service = CopilotSupportService(
            data_access=self._data_access,
            logger=logger,
            max_figure_size=MAX_FIGURE_SIZE,
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
        # The builder calls back into this instance, so a loader replaced on
        # it (tests, alternative data sources) is the one it uses.
        self._task_context_builder = TaskContextBuilder(
            load_qubit_params=self._context_load_qubit_params,
            load_task_result=self._context_load_task_result,
            load_task_history=self._context_load_task_history,
            load_neighbor_qubit_params=self._context_load_neighbor_qubit_params,
            load_coupling_params=self._context_load_coupling_params,
            load_figure_as_base64=self._context_load_figure_as_base64,
            load_figures_as_base64=self._context_load_figures_as_base64,
            collect_expected_images=self._context_collect_expected_images,
        )

    def _context_load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]:
        return self.load_qubit_params(chip_id, qid)

    def _context_load_task_result(self, task_id: str) -> dict[str, Any] | None:
        return self.load_task_result(task_id)

    def _context_load_task_history(
        self, task_name: str, chip_id: str, qid: str, last_n: int
    ) -> list[dict[str, Any]]:
        return self.load_task_history(task_name, chip_id, qid, last_n)

    def _context_load_neighbor_qubit_params(
        self, chip_id: str, qid: str, params: list[str] | None
    ) -> dict[str, dict[str, Any]]:
        return self.load_neighbor_qubit_params(chip_id, qid, params)

    def _context_load_coupling_params(
        self, chip_id: str, qid: str, params: list[str] | None
    ) -> dict[str, dict[str, Any]]:
        return self.load_coupling_params(chip_id, qid, params)

    def _context_load_figure_as_base64(self, figure_paths: list[str]) -> str | None:
        return self.load_figure_as_base64(figure_paths)

    def _context_load_figures_as_base64(self, figure_paths: list[str]) -> list[tuple[str, str]]:
        return self.load_figures_as_base64(figure_paths)

    def _context_collect_expected_images(
        self,
        knowledge: Any,
        max_images: int | None = None,
        *,
        include_case_images: bool = True,
        include_review_images: bool = True,
    ) -> list[tuple[str, str]]:
        return self.collect_expected_images(
            knowledge,
            max_images=max_images,
            include_case_images=include_case_images,
            include_review_images=include_review_images,
        )

    def load_default_chip_id(self) -> str | None:
        """Load the most recently installed chip_id from DB."""
        return self._support_service.load_default_chip_id()

    def load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]:
        """Load current qubit parameters from QubitDocument.data."""
        return self._support_service.load_qubit_params(chip_id, qid)

    def load_task_result(self, task_id: str) -> dict[str, Any] | None:
        """Load a task result as a plain dict."""
        return self._support_service.load_task_result(task_id)

    def load_figure_as_base64(self, figure_paths: list[str]) -> str | None:
        """Load the first figure of a task result as base64."""
        return self._support_service.load_figure_as_base64(figure_paths)

    def load_figures_as_base64(self, figure_paths: list[str]) -> list[tuple[str, str]]:
        """Load every figure of a task result as (base64, alt text)."""
        return self._support_service.load_figures_as_base64(figure_paths)

    def collect_expected_images(
        self,
        knowledge: Any,
        max_images: int | None = None,
        *,
        include_case_images: bool = True,
        include_review_images: bool = True,
    ) -> list[tuple[str, str]]:
        """Reference images from the task's knowledge, as (base64, alt text)."""
        return self._support_service.collect_expected_images(
            knowledge,
            max_images=max_images,
            include_case_images=include_case_images,
            include_review_images=include_review_images,
        )

    def load_task_history(
        self, task_name: str, chip_id: str, qid: str, last_n: int = 5
    ) -> list[dict[str, Any]]:
        """Recent completed runs of a task for one target."""
        return self._history_loader.load_task_history(
            task_name=task_name, chip_id=chip_id, qid=qid, last_n=last_n
        )

    def load_neighbor_qubit_params(
        self, chip_id: str, qid: str, param_names: list[str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Parameters of the qubits coupled to one qubit."""
        return self._topology_context_loader.load_neighbor_qubit_params(
            chip_id=chip_id, qid=qid, param_names=param_names or []
        )

    def load_coupling_params(
        self, chip_id: str, qid: str, param_names: list[str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Parameters of the couplings of one qubit."""
        return self._topology_context_loader.load_coupling_params(
            chip_id=chip_id, qid=qid, param_names=param_names or []
        )

    def build_task_context(
        self,
        task_name: str,
        chip_id: str,
        qid: str,
        task_id: str,
        image_base64: str | None,
        config: CopilotConfig,
    ) -> TaskContextBundle:
        """Build the context a chat about one task result opens with."""
        return self._task_context_builder.build_task_context(
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
        experiment_images: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Build the ``images_sent`` metadata dict for a task chat answer."""
        return CopilotSupportService.build_images_sent_metadata(
            image_base64=image_base64,
            figure_paths=figure_paths,
            expected_images=expected_images,
            task_name=task_name,
            experiment_images=experiment_images,
        )
