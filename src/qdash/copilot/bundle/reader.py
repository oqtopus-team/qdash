"""Readers for AI review replay bundles."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from qdash.copilot.bundle.models import (
    AIReviewBundleContext,
    AIReviewBundleManifest,
    AIReviewRuntimeConfig,
)


def _read_json(zf: ZipFile, path: str) -> dict:
    return json.loads(zf.read(path).decode("utf-8"))


def load_ai_review_bundle(
    path: str | Path,
) -> tuple[AIReviewBundleManifest, AIReviewBundleContext, AIReviewRuntimeConfig, str]:
    """Load the canonical bundle components from a replay bundle zip file."""
    with ZipFile(path) as zf:
        manifest = AIReviewBundleManifest.model_validate(_read_json(zf, "manifest.json"))
        bundle_context = AIReviewBundleContext.model_validate(_read_json(zf, "context.json"))
        runtime_config = AIReviewRuntimeConfig.model_validate(_read_json(zf, "copilot_config.json"))
        prompt_text = zf.read("prompt.txt").decode("utf-8")
    return manifest, bundle_context, runtime_config, prompt_text


def load_ai_review_bundle_metadata(path: str | Path) -> dict[str, dict]:
    """Load optional metadata JSON files stored under ``metadata/``."""
    metadata: dict[str, dict] = {}
    with ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith("metadata/") or not name.endswith(".json"):
                continue
            key = Path(name).stem
            metadata[key] = _read_json(zf, name)
    return metadata
