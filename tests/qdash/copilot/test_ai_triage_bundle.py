"""Tests for AI triage replay bundle models, writer, reader, and exporter."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zipfile import ZipFile

from qdash.copilot.bundle.exporters.ai_triage import export_ai_triage_replay_bundle
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
from qdash.copilot.bundle.reader import load_ai_triage_bundle, load_ai_triage_bundle_metadata
from qdash.copilot.bundle.writer import write_ai_triage_bundle
from qdash.copilot.config import AnalysisConfig, CopilotConfig, ModelConfig
from qdash.copilot.contracts import AnalysisContextResult, TaskAnalysisContext

if TYPE_CHECKING:
    from pathlib import Path


def _config() -> CopilotConfig:
    return CopilotConfig(
        enabled=True,
        response_language="ja",
        thinking_language="en",
        model=ModelConfig(provider="openai", name="gpt-4.1"),
        analysis_models=[ModelConfig(provider="openai", name="gpt-5.1", max_output_tokens=2048)],
        analysis=AnalysisConfig(
            enabled=True,
            max_expected_images=2,
            ai_triage_tasks=["CheckQubitSpectroscopy"],
            ai_triage_message="Review this run carefully.",
        ),
    )


def _context() -> TaskAnalysisContext:
    return TaskAnalysisContext(
        task_knowledge_prompt="knowledge-v1",
        chip_id="chip-1",
        qid="4",
        qubit_params={"t1": 12.3},
        input_parameters={"freq": 4.2},
        output_parameters={"coarse_qubit_frequency": {"value": 4.21}},
        run_parameters={},
    )


def _model_ref() -> AITriageModelRef:
    return AITriageModelRef(
        provider="openai",
        name="gpt-5.1",
        api_style="responses",
        temperature=0.7,
        max_output_tokens=2048,
    )


def _runtime_config() -> AITriageRuntimeConfig:
    return AITriageRuntimeConfig(
        enabled=True,
        response_language="ja",
        thinking_language="en",
        model=AITriageModelRef(
            provider="openai",
            name="gpt-4.1",
            api_style="responses",
            temperature=0.7,
            max_output_tokens=16384,
        ),
        analysis_model=_model_ref(),
        ai_triage_message="Review this run carefully.",
        max_expected_images=2,
    )


def _manifest() -> AITriageBundleManifest:
    return AITriageBundleManifest(
        created_at=datetime(2026, 5, 14, tzinfo=UTC),
        source=AITriageBundleSource(
            project_id="proj-1",
            chip_id="chip-1",
            qid="4",
            task_name="CheckQubitSpectroscopy",
            task_id="task-1",
            execution_id="exec-1",
            trigger="chip_page",
        ),
        selected_model=_model_ref(),
        knowledge=AITriageKnowledgeRef(
            task_name="CheckQubitSpectroscopy",
            task_path="cw-characterization/CheckQubitSpectroscopy/index.md",
        ),
        inputs=AITriageBundleInputs(
            expected_image_paths=["expected_images/00.png"],
            experiment_image_paths=["experiment_images/00.png"],
            figure_paths=["figures/00.png", "figures/01.json"],
            extra_paths=["metadata/source_task_result.json"],
        ),
    )


def _bundle_context(tmp_path: Path) -> AITriageBundleContext:
    figure_png = tmp_path / "figure.png"
    figure_png.write_bytes(b"png-bytes")
    figure_json = tmp_path / "figure.json"
    figure_json.write_text('{"value": 1}', encoding="utf-8")
    return AITriageBundleContext(
        context=_context(),
        image_base64=base64.b64encode(b"experiment").decode("utf-8"),
        expected_images=[
            AITriageImageEntry(
                path="expected_images/00.png",
                alt_text="expected image",
                base64_data=base64.b64encode(b"expected").decode("utf-8"),
            )
        ],
        figures=[
            AITriageFigureEntry(source_path=str(figure_png), archive_path="figures/00.png"),
            AITriageFigureEntry(source_path=str(figure_json), archive_path="figures/01.json"),
        ],
    )


def _analysis_context_result(tmp_path: Path) -> AnalysisContextResult:
    figure_png = tmp_path / "figure.png"
    figure_png.write_bytes(b"png-bytes")
    figure_json = tmp_path / "figure.json"
    figure_json.write_text('{"value": 1}', encoding="utf-8")
    return AnalysisContextResult(
        context=_context(),
        image_base64=base64.b64encode(b"experiment").decode("utf-8"),
        expected_images=[(base64.b64encode(b"expected").decode("utf-8"), "expected image")],
        figure_paths=[str(figure_png), str(figure_json)],
    )


def test_write_and_read_ai_triage_bundle_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "bundle.zip"
    write_ai_triage_bundle(
        output_path=output_path,
        manifest=_manifest(),
        bundle_context=_bundle_context(tmp_path),
        runtime_config=_runtime_config(),
        prompt_text="triage prompt",
        extra_metadata={"source_task_result": {"task_id": "task-1"}},
    )

    manifest, bundle_context, runtime_config, prompt_text = load_ai_triage_bundle(output_path)
    metadata = load_ai_triage_bundle_metadata(output_path)

    assert manifest.source.task_id == "task-1"
    assert bundle_context.context.task_knowledge_prompt == "knowledge-v1"
    assert runtime_config.ai_triage_message == "Review this run carefully."
    assert prompt_text.strip() == "triage prompt"
    assert metadata["source_task_result"]["task_id"] == "task-1"

    with ZipFile(output_path) as zf:
        assert "expected_images/00.png" in zf.namelist()
        assert "experiment_images/00.png" in zf.namelist()
        assert "figures/00.png" in zf.namelist()
        assert "figures/01.json" in zf.namelist()


def test_export_ai_triage_replay_bundle_uses_shared_triage_inputs(tmp_path: Path) -> None:
    output_path = tmp_path / "exported.zip"
    config = _config()
    context_bundle = _analysis_context_result(tmp_path)

    from unittest.mock import patch

    with (
        patch("qdash.copilot.bundle.exporters.ai_triage.load_copilot_config", return_value=config),
        patch(
            "qdash.copilot.bundle.exporters.ai_triage.build_ai_triage_context",
            return_value=context_bundle,
        ),
        patch(
            "qdash.copilot.bundle.exporters.ai_triage.get_task_knowledge_repo_metadata",
            return_value=("https://github.com/example/qdash-task-knowledge.git", "abc123def456"),
        ),
    ):
        result_path = export_ai_triage_replay_bundle(
            task_name="CheckQubitSpectroscopy",
            chip_id="chip-1",
            qid="4",
            task_id="task-1",
            trigger="chip_page",
            project_id="proj-1",
            execution_id="exec-1",
            output_path=output_path,
        )

    assert result_path == output_path
    manifest, bundle_context, runtime_config, prompt_text = load_ai_triage_bundle(output_path)
    metadata = load_ai_triage_bundle_metadata(output_path)

    assert manifest.source.trigger == "chip_page"
    assert manifest.knowledge.task_path == "cw-characterization/CheckQubitSpectroscopy/index.md"
    assert manifest.knowledge.repo_url == "https://github.com/example/qdash-task-knowledge.git"
    assert manifest.knowledge.commit == "abc123def456"
    assert manifest.selected_model.name == "gpt-5.1"
    assert manifest.inputs.expected_image_paths == ["expected_images/00.png"]
    assert manifest.inputs.figure_paths == ["figures/00.png", "figures/01.json"]
    assert bundle_context.context.qid == "4"
    assert runtime_config.analysis_model is not None
    assert runtime_config.analysis_model.name == "gpt-5.1"
    assert "Review this run carefully." in prompt_text
    assert metadata["source_task_result"]["execution_id"] == "exec-1"
    assert metadata["knowledge_ref"]["task_path"] == (
        "cw-characterization/CheckQubitSpectroscopy/index.md"
    )
    assert (
        metadata["knowledge_ref"]["repo_url"]
        == "https://github.com/example/qdash-task-knowledge.git"
    )
    assert metadata["knowledge_ref"]["commit"] == "abc123def456"

    with ZipFile(output_path) as zf:
        assert json.loads(zf.read("manifest.json").decode("utf-8"))["bundle_type"] == (
            "ai_triage_replay"
        )
