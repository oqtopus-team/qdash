"""Writers for AI triage replay bundles."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile

if TYPE_CHECKING:
    from qdash.copilot.bundle.models import (
        AITriageBundleContext,
        AITriageBundleManifest,
        AITriageRuntimeConfig,
    )


def _json_bytes(data: dict) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _decode_base64(data: str) -> bytes:
    return base64.b64decode(data.encode("utf-8"))


def _safe_read_file(path: str | Path) -> bytes | None:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None
    return file_path.read_bytes()


def write_ai_triage_bundle(
    *,
    output_path: str | Path,
    manifest: AITriageBundleManifest,
    bundle_context: AITriageBundleContext,
    runtime_config: AITriageRuntimeConfig,
    prompt_text: str,
    extra_metadata: dict[str, dict] | None = None,
) -> Path:
    """Write an AI triage replay bundle zip file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _json_bytes(manifest.model_dump(mode="json")))
        zf.writestr("context.json", _json_bytes(bundle_context.model_dump(mode="json")))
        zf.writestr("copilot_config.json", _json_bytes(runtime_config.model_dump(mode="json")))
        zf.writestr("prompt.txt", prompt_text.rstrip() + "\n")

        if bundle_context.experiment_images:
            for image in bundle_context.experiment_images:
                zf.writestr(image.path, _decode_base64(image.base64_data))
        elif bundle_context.image_base64:
            zf.writestr("experiment_images/00.png", _decode_base64(bundle_context.image_base64))

        for image in bundle_context.expected_images:
            zf.writestr(image.path, _decode_base64(image.base64_data))

        for figure in bundle_context.figures:
            content = _safe_read_file(figure.source_path)
            if content is None:
                continue
            zf.writestr(figure.archive_path, content)

        for name, payload in (extra_metadata or {}).items():
            zf.writestr(f"metadata/{name}.json", _json_bytes(payload))

    return output_path
