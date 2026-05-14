"""Readers for AI triage replay bundles."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from qdash.copilot.bundle.models import (
    AITriageBundleContext,
    AITriageBundleManifest,
    AITriageRuntimeConfig,
)


def _read_json(zf: ZipFile, path: str) -> dict:
    return json.loads(zf.read(path).decode("utf-8"))


def load_ai_triage_bundle(
    path: str | Path,
) -> tuple[AITriageBundleManifest, AITriageBundleContext, AITriageRuntimeConfig, str]:
    """Load the canonical bundle components from a replay bundle zip file."""
    with ZipFile(path) as zf:
        manifest = AITriageBundleManifest.model_validate(_read_json(zf, "manifest.json"))
        bundle_context = AITriageBundleContext.model_validate(_read_json(zf, "context.json"))
        runtime_config = AITriageRuntimeConfig.model_validate(_read_json(zf, "copilot_config.json"))
        prompt_text = zf.read("prompt.txt").decode("utf-8")
    return manifest, bundle_context, runtime_config, prompt_text


def load_ai_triage_bundle_metadata(path: str | Path) -> dict[str, dict]:
    """Load optional metadata JSON files stored under ``metadata/``."""
    metadata: dict[str, dict] = {}
    with ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith("metadata/") or not name.endswith(".json"):
                continue
            key = Path(name).stem
            metadata[key] = _read_json(zf, name)
    return metadata
