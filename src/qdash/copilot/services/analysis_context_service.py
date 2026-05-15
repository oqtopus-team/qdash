"""Analysis-context assembly helpers for Copilot task review flows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from qdash.copilot.config import CopilotConfig
    from qdash.copilot.contracts import AnalysisContextResult


class AnalysisContextBuilder:
    """Build task-analysis context from task knowledge and repository-backed loaders."""

    def __init__(
        self,
        *,
        load_qubit_params: Callable[[str, str], dict[str, Any]],
        load_task_result: Callable[[str], dict[str, Any] | None],
        load_task_history: Callable[[str, str, str, int], list[dict[str, Any]]],
        load_neighbor_qubit_params: Callable[
            [str, str, list[str] | None], dict[str, dict[str, Any]]
        ],
        load_coupling_params: Callable[[str, str, list[str] | None], dict[str, dict[str, Any]]],
        load_figure_as_base64: Callable[[list[str]], str | None],
        load_figures_as_base64: Callable[[list[str]], list[tuple[str, str]]],
        collect_expected_images: Callable[[Any, int | None], list[tuple[str, str]]],
    ) -> None:
        self._load_qubit_params = load_qubit_params
        self._load_task_result = load_task_result
        self._load_task_history = load_task_history
        self._load_neighbor_qubit_params = load_neighbor_qubit_params
        self._load_coupling_params = load_coupling_params
        self._load_figure_as_base64 = load_figure_as_base64
        self._load_figures_as_base64 = load_figures_as_base64
        self._collect_expected_images = collect_expected_images

    def build_analysis_context(
        self,
        *,
        task_name: str,
        chip_id: str,
        qid: str,
        task_id: str,
        image_base64: str | None,
        config: CopilotConfig,
    ) -> AnalysisContextResult:
        """Build the full analysis context consumed by Copilot review flows."""
        from qdash.copilot.contracts import (
            AnalysisContextResult,
            TaskAnalysisContext,
        )
        from qdash.datamodel.task_knowledge import get_task_knowledge

        knowledge = get_task_knowledge(task_name)
        knowledge_prompt = self._build_task_knowledge_prompt(task_name, knowledge)
        qubit_params = self._load_qubit_params(chip_id, qid)
        task_result = self._load_task_result(task_id)
        input_params, output_params, run_params, figure_paths = self._extract_task_result_payload(
            task_result
        )
        history_results, neighbor_qubit_params, coupling_params = (
            self._load_related_analysis_context(
                task_name=task_name,
                chip_id=chip_id,
                qid=qid,
                knowledge=knowledge,
            )
        )
        image_base64, expected_images, experiment_images = self._resolve_analysis_images(
            knowledge=knowledge,
            task_result=task_result,
            figure_paths=figure_paths,
            image_base64=image_base64,
            config=config,
        )

        context = TaskAnalysisContext(
            task_knowledge_prompt=knowledge_prompt,
            chip_id=chip_id,
            qid=qid,
            qubit_params=qubit_params,
            input_parameters=input_params,
            output_parameters=output_params,
            run_parameters=run_params,
            history_results=history_results,
            neighbor_qubit_params=neighbor_qubit_params,
            coupling_params=coupling_params,
        )
        return AnalysisContextResult(
            context=context,
            image_base64=image_base64,
            expected_images=expected_images,
            experiment_images=experiment_images,
            figure_paths=figure_paths,
        )

    @staticmethod
    def _build_task_knowledge_prompt(task_name: str, knowledge: Any) -> str:
        """Build the prompt prefix from task knowledge or fall back to the task name."""
        return knowledge.to_prompt() if knowledge else f"Task: {task_name}"

    @staticmethod
    def _extract_task_result_payload(
        task_result: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
        """Extract task-result fields used by analysis context assembly."""
        if not task_result:
            return {}, {}, {}, []
        return (
            task_result.get("input_parameters", {}),
            task_result.get("output_parameters", {}),
            task_result.get("run_parameters", {}),
            task_result.get("figure_path", []),
        )

    def _load_related_analysis_context(
        self,
        *,
        task_name: str,
        chip_id: str,
        qid: str,
        knowledge: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        """Load history and neighborhood context declared by task knowledge."""
        history_results: list[dict[str, Any]] = []
        neighbor_qubit_params: dict[str, dict[str, Any]] = {}
        coupling_params: dict[str, dict[str, Any]] = {}
        if not knowledge or not knowledge.related_context:
            return history_results, neighbor_qubit_params, coupling_params

        for related_context in knowledge.related_context:
            if related_context.type == "history":
                history_results = self._load_task_history(
                    task_name, chip_id, qid, related_context.last_n
                )
            elif related_context.type == "neighbor_qubits":
                neighbor_qubit_params = self._load_neighbor_qubit_params(
                    chip_id, qid, related_context.params
                )
            elif related_context.type == "coupling":
                coupling_params = self._load_coupling_params(chip_id, qid, related_context.params)

        return history_results, neighbor_qubit_params, coupling_params

    def _resolve_analysis_images(
        self,
        *,
        knowledge: Any,
        task_result: dict[str, Any] | None,
        figure_paths: list[str],
        image_base64: str | None,
        config: CopilotConfig,
    ) -> tuple[str | None, list[tuple[str, str]], list[tuple[str, str]]]:
        """Resolve experiment and expected images for multimodal analysis."""
        expected_images: list[tuple[str, str]] = []
        experiment_images: list[tuple[str, str]] = []
        if not config.analysis.multimodal:
            return image_base64, expected_images, experiment_images

        if task_result:
            experiment_images = self._load_figures_as_base64(figure_paths)
        if not image_base64:
            image_base64 = experiment_images[0][0] if experiment_images else None
        expected_images = self._collect_expected_images(
            knowledge,
            config.analysis.max_expected_images,
        )
        return image_base64, expected_images, experiment_images
