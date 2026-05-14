"""Export AI triage replay bundles from the production triage path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from qdash.copilot.bundle.models import (
    AITriageBundleContext,
    AITriageBundleInputs,
    AITriageBundleManifest,
    AITriageBundleSource,
    AITriageFigureEntry,
    AITriageImageEntry,
    AITriageKnowledgeRef,
    AITriageModelRef,
    AITriageRuntimeConfig,
)
from qdash.copilot.bundle.writer import write_ai_triage_bundle
from qdash.copilot.config import CopilotConfig, ModelConfig, load_copilot_config
from qdash.copilot.triage import (
    apply_ai_triage_config,
    build_ai_triage_context,
    build_ai_triage_user_message,
    select_analysis_model,
)
from qdash.datamodel.task_knowledge import get_task_category_dir, get_task_knowledge_repo_metadata


def _model_ref(model: ModelConfig) -> AITriageModelRef:
    return AITriageModelRef(
        provider=model.provider,
        name=model.name,
        api_style=model.api_style,
        temperature=model.temperature,
        max_output_tokens=model.max_output_tokens,
        reasoning_effort=model.reasoning_effort,
    )


def _runtime_config(config: CopilotConfig) -> AITriageRuntimeConfig:
    return AITriageRuntimeConfig(
        enabled=config.enabled,
        response_language=config.response_language,
        thinking_language=config.thinking_language,
        model=_model_ref(config.model),
        analysis_model=_model_ref(config.analysis_model) if config.analysis_model else None,
        ai_triage_message=config.analysis.ai_triage_message,
        max_expected_images=config.analysis.max_expected_images,
        ai_triage_max_expected_images=config.analysis.ai_triage_max_expected_images,
        ai_triage_max_output_tokens=config.analysis.ai_triage_max_output_tokens,
    )


def _knowledge_ref(task_name: str) -> AITriageKnowledgeRef:
    category_dir = get_task_category_dir(task_name)
    task_path = None if category_dir == "other" else f"{category_dir}/{task_name}/index.md"
    repo_url, commit = get_task_knowledge_repo_metadata()
    return AITriageKnowledgeRef(
        repo_url=repo_url,
        commit=commit,
        task_path=task_path,
        task_name=task_name,
    )


def _figure_entries(figure_paths: list[str]) -> list[AITriageFigureEntry]:
    entries: list[AITriageFigureEntry] = []
    for index, source_path in enumerate(figure_paths):
        suffix = Path(source_path).suffix or ".bin"
        entries.append(
            AITriageFigureEntry(
                source_path=source_path,
                archive_path=f"figures/{index:02d}{suffix}",
            )
        )
    return entries


def _bundle_context(context_bundle: Any) -> AITriageBundleContext:
    return AITriageBundleContext(
        context=context_bundle.context,
        image_base64=context_bundle.image_base64,
        expected_images=[
            AITriageImageEntry(
                path=f"expected_images/{index:02d}.png",
                alt_text=alt_text,
                base64_data=base64_data,
            )
            for index, (base64_data, alt_text) in enumerate(context_bundle.expected_images)
        ],
        figures=_figure_entries(list(context_bundle.figure_paths)),
    )


def export_ai_triage_replay_bundle(
    *,
    task_name: str,
    chip_id: str,
    qid: str,
    task_id: str,
    trigger: Literal["workflow", "chip_page", "bulk_request"],
    output_path: str | Path,
    project_id: str | None = None,
    execution_id: str | None = None,
    model_override: ModelConfig | None = None,
    extra_metadata: dict[str, dict] | None = None,
) -> Path:
    """Export a replayable AI triage bundle using the production triage inputs."""
    config = load_copilot_config()
    if model_override is not None:
        config = config.model_copy(update={"analysis_model": model_override})
    config = apply_ai_triage_config(config)

    context_bundle = build_ai_triage_context(
        task_name=task_name,
        chip_id=chip_id,
        qid=qid,
        task_id=task_id,
        config=config,
    )
    prompt_text = build_ai_triage_user_message(config)
    selected_model = select_analysis_model(config)
    bundle_context = _bundle_context(context_bundle)

    manifest = AITriageBundleManifest(
        created_at=datetime.now(UTC),
        source=AITriageBundleSource(
            project_id=project_id,
            chip_id=chip_id,
            qid=qid,
            task_name=task_name,
            task_id=task_id,
            execution_id=execution_id,
            trigger=trigger,
        ),
        selected_model=_model_ref(selected_model),
        knowledge=_knowledge_ref(task_name),
        inputs=AITriageBundleInputs(
            context_path="context.json",
            prompt_path="prompt.txt",
            copilot_config_path="copilot_config.json",
            expected_image_paths=[image.path for image in bundle_context.expected_images],
            experiment_image_paths=(
                ["experiment_images/00.png"] if bundle_context.image_base64 else []
            ),
            figure_paths=[figure.archive_path for figure in bundle_context.figures],
            extra_paths=(
                [f"metadata/{name}.json" for name in extra_metadata] if extra_metadata else []
            ),
        ),
    )

    metadata_payload = {
        "source_task_result": {
            "project_id": project_id,
            "chip_id": chip_id,
            "qid": qid,
            "task_name": task_name,
            "task_id": task_id,
            "execution_id": execution_id,
            "trigger": trigger,
        },
        "knowledge_ref": manifest.knowledge.model_dump(mode="json"),
    }
    if extra_metadata:
        metadata_payload.update(extra_metadata)

    return write_ai_triage_bundle(
        output_path=output_path,
        manifest=manifest,
        bundle_context=bundle_context,
        runtime_config=_runtime_config(config),
        prompt_text=prompt_text,
        extra_metadata=metadata_payload,
    )
