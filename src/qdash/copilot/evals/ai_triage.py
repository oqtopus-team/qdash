"""Capture and replay AI triage runs for prompt and context tuning."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from qdash.copilot.config import CopilotConfig, ModelConfig, load_copilot_config
from qdash.copilot.contracts import AnalysisContextResult, TaskAnalysisContext
from qdash.copilot.triage import (
    apply_ai_triage_config,
    build_ai_triage_context,
    build_ai_triage_user_message,
    build_model_override,
    render_ai_triage_markdown,
    select_analysis_model,
)

SnapshotMode = Literal["frozen", "rebuild"]


class AITriageExpectedImage(BaseModel):
    """Serialized expected image entry for a snapshot."""

    alt_text: str
    base64_data: str


class AITriageSourceRef(BaseModel):
    """Reference to the source task result that produced the snapshot."""

    task_name: str
    chip_id: str
    qid: str
    task_id: str


class AITriageModelRef(BaseModel):
    """Compact model metadata stored with a snapshot or replay result."""

    provider: str
    name: str
    api_style: str
    max_output_tokens: int
    temperature: float | None = None
    reasoning_effort: str | None = None


class AITriageEvalSnapshot(BaseModel):
    """Frozen AI triage input that can be replayed later."""

    snapshot_version: int = 1
    captured_at: datetime
    source: AITriageSourceRef
    selected_model: AITriageModelRef
    user_message: str
    context: TaskAnalysisContext
    image_base64: str | None = None
    expected_images: list[AITriageExpectedImage] = Field(default_factory=list)
    figure_paths: list[str] = Field(default_factory=list)


class AITriageEvalRunResult(BaseModel):
    """Replay result and supporting artifacts for one AI triage run."""

    run_at: datetime
    mode: SnapshotMode
    source: AITriageSourceRef
    selected_model: AITriageModelRef
    user_message: str
    context: TaskAnalysisContext
    image_base64: str | None = None
    expected_images: list[AITriageExpectedImage] = Field(default_factory=list)
    markdown: str


def _model_ref(model: ModelConfig) -> AITriageModelRef:
    return AITriageModelRef(
        provider=model.provider,
        name=model.name,
        api_style=model.api_style,
        max_output_tokens=model.max_output_tokens,
        temperature=model.temperature,
        reasoning_effort=model.reasoning_effort,
    )


def _bundle_to_expected_images(bundle: AnalysisContextResult) -> list[AITriageExpectedImage]:
    return [
        AITriageExpectedImage(alt_text=alt_text, base64_data=base64_data)
        for base64_data, alt_text in bundle.expected_images
    ]


def _snapshot_to_bundle(snapshot: AITriageEvalSnapshot) -> AnalysisContextResult:
    return AnalysisContextResult(
        context=snapshot.context,
        image_base64=snapshot.image_base64,
        expected_images=[(image.base64_data, image.alt_text) for image in snapshot.expected_images],
        figure_paths=list(snapshot.figure_paths),
    )


def capture_ai_triage_snapshot(
    *,
    task_name: str,
    chip_id: str,
    qid: str,
    task_id: str,
    config: CopilotConfig | None = None,
    model_override: ModelConfig | None = None,
) -> AITriageEvalSnapshot:
    """Capture a replayable AI triage snapshot from the live production path."""
    config = apply_ai_triage_config(config or load_copilot_config())
    if model_override is not None:
        config = config.model_copy(update={"analysis_model": model_override})

    bundle = build_ai_triage_context(
        task_name=task_name,
        chip_id=chip_id,
        qid=qid,
        task_id=task_id,
        config=config,
    )
    return AITriageEvalSnapshot(
        captured_at=datetime.now(UTC),
        source=AITriageSourceRef(
            task_name=task_name,
            chip_id=chip_id,
            qid=qid,
            task_id=task_id,
        ),
        selected_model=_model_ref(select_analysis_model(config)),
        user_message=build_ai_triage_user_message(config),
        context=bundle.context,
        image_base64=bundle.image_base64,
        expected_images=_bundle_to_expected_images(bundle),
        figure_paths=list(bundle.figure_paths),
    )


def run_ai_triage_snapshot(
    snapshot: AITriageEvalSnapshot,
    *,
    mode: SnapshotMode = "frozen",
    config: CopilotConfig | None = None,
    model_override: ModelConfig | None = None,
    use_snapshot_message: bool = False,
) -> AITriageEvalRunResult:
    """Replay one AI triage snapshot through the same renderer as production."""
    config = apply_ai_triage_config(config or load_copilot_config())
    if model_override is not None:
        config = config.model_copy(update={"analysis_model": model_override})

    if mode == "rebuild":
        bundle = build_ai_triage_context(
            task_name=snapshot.source.task_name,
            chip_id=snapshot.source.chip_id,
            qid=snapshot.source.qid,
            task_id=snapshot.source.task_id,
            config=config,
        )
    else:
        bundle = _snapshot_to_bundle(snapshot)

    user_message = (
        snapshot.user_message if use_snapshot_message else build_ai_triage_user_message(config)
    )
    markdown = render_ai_triage_markdown(
        task_name=snapshot.source.task_name,
        config=config,
        context_bundle=bundle,
        user_message=user_message,
    )
    return AITriageEvalRunResult(
        run_at=datetime.now(UTC),
        mode=mode,
        source=snapshot.source,
        selected_model=_model_ref(select_analysis_model(config)),
        user_message=user_message,
        context=bundle.context,
        image_base64=bundle.image_base64,
        expected_images=_bundle_to_expected_images(bundle),
        markdown=markdown,
    )


def save_ai_triage_snapshot(snapshot: AITriageEvalSnapshot, path: str | Path) -> None:
    """Persist a snapshot as JSON."""
    Path(path).write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def load_ai_triage_snapshot(path: str | Path) -> AITriageEvalSnapshot:
    """Load a snapshot JSON file."""
    return AITriageEvalSnapshot.model_validate_json(Path(path).read_text(encoding="utf-8"))


def write_ai_triage_run_artifacts(result: AITriageEvalRunResult, output_dir: str | Path) -> Path:
    """Write replay artifacts for prompt/context inspection."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "result.md").write_text(result.markdown + "\n", encoding="utf-8")
    (output_path / "context.json").write_text(
        json.dumps(result.context.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_path / "report.json").write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return output_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and replay AI triage runs for prompt/context tuning."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture", help="Capture one live AI triage snapshot.")
    capture_parser.add_argument("--task-name", required=True)
    capture_parser.add_argument("--chip-id", required=True)
    capture_parser.add_argument("--qid", required=True)
    capture_parser.add_argument("--task-id", required=True)
    capture_parser.add_argument("--output", required=True)
    _add_model_override_args(capture_parser)

    run_parser = subparsers.add_parser("run", help="Replay a captured AI triage snapshot.")
    run_parser.add_argument("--snapshot", required=True)
    run_parser.add_argument("--mode", choices=("frozen", "rebuild"), default="frozen")
    run_parser.add_argument("--output-dir", required=True)
    run_parser.add_argument("--use-snapshot-message", action="store_true")
    run_parser.add_argument("--print-markdown", action="store_true")
    _add_model_override_args(run_parser)
    return parser


def _add_model_override_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model-provider")
    parser.add_argument("--model-name")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--api-style")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")


def _resolve_model_override(args: argparse.Namespace, config: CopilotConfig) -> ModelConfig | None:
    if not any(
        getattr(args, field) is not None
        for field in (
            "model_provider",
            "model_name",
            "temperature",
            "max_output_tokens",
            "reasoning_effort",
            "api_style",
            "base_url",
            "api_key_env",
        )
    ):
        return None

    base_model = select_analysis_model(apply_ai_triage_config(config))
    return build_model_override(
        base_model=base_model,
        provider=args.model_provider,
        name=args.model_name,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        reasoning_effort=args.reasoning_effort,
        api_style=args.api_style,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
    )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    config = load_copilot_config()
    model_override = _resolve_model_override(args, config)

    if args.command == "capture":
        snapshot = capture_ai_triage_snapshot(
            task_name=args.task_name,
            chip_id=args.chip_id,
            qid=args.qid,
            task_id=args.task_id,
            config=config,
            model_override=model_override,
        )
        save_ai_triage_snapshot(snapshot, args.output)
        print(Path(args.output))
        return 0

    snapshot = load_ai_triage_snapshot(args.snapshot)
    result = run_ai_triage_snapshot(
        snapshot,
        mode=args.mode,
        config=config,
        model_override=model_override,
        use_snapshot_message=args.use_snapshot_message,
    )
    output_dir = write_ai_triage_run_artifacts(result, args.output_dir)
    if args.print_markdown:
        print(result.markdown)
    else:
        print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
