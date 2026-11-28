"""Generate ``qdash.sdk._generated`` from ``docs/oas/openapi.json``.

The package has two generated parts, both derived from the OpenAPI document in place:

* The API client: Fern's Python SDK generator, run in local mode with the CLI and generator
  versions pinned in ``sdks/python/fern``. It needs Node.js (``npx``) and Docker; no Fern
  account or token. Only the Python sources are kept.
* ``_authoring.py``: strict Pydantic models of the request bodies the SDK builds locally
  (pipeline specs, dashboards, metric scripts). Fern's models accept unknown fields and drop
  ``pattern``, ``const`` and default constraints, so these schemas are generated again with
  datamodel-code-generator, with the options of the qdash-client models, from the subset of
  the document they reference.

``--check`` regenerates into a temporary tree and fails when the committed package differs.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENAPI = REPO_ROOT / "docs/oas/openapi.json"
FERN_DIR = REPO_ROOT / "sdks/python/fern"
# generators.yml writes the Fern output here; build/ is ignored by git.
FERN_OUTPUT = REPO_ROOT / "sdks/python/build/fern-python"
TARGET = REPO_ROOT / "sdks/python/src/qdash/sdk/_generated"
AUTHORING_MODULE = "_authoring.py"
FERN_GROUP = "python-sdk"

# Request bodies the SDK builds locally; their referenced schemas are generated too.
AUTHORING_ROOTS = (
    "CalibrationPipelineSpec",
    "DashboardCreateRequest",
    "DashboardUpdateRequest",
    "MetricScriptPanelConfig",
    "MetricScriptCreateRequest",
    "MetricScriptUpdateRequest",
    "MetricScriptEvaluateRequest",
    "RelativePeriod",
    "AbsolutePeriod",
)


def _fern_cli_version() -> str:
    config = json.loads((FERN_DIR / "fern.config.json").read_text(encoding="utf-8"))
    return str(config["version"])


def _run_fern() -> dict[str, bytes]:
    """Run the pinned Fern generator and return its Python sources by relative path."""
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("generating qdash.sdk needs npx (Node.js) and Docker on PATH")
    if FERN_OUTPUT.exists():
        shutil.rmtree(FERN_OUTPUT)
    result = subprocess.run(  # noqa: S603
        [
            npx,
            "--yes",
            f"fern-api@{_fern_cli_version()}",
            "generate",
            "--group",
            FERN_GROUP,
            "--local",
            "--force",
        ],
        cwd=FERN_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit("Fern generation failed (is Docker running?)")
    files = {
        path.relative_to(FERN_OUTPUT).as_posix(): path.read_bytes()
        for path in sorted(FERN_OUTPUT.rglob("*.py"))
        # .fern/ holds run metadata (git commit, dirty flag), not package sources.
        if ".fern" not in path.relative_to(FERN_OUTPUT).parts
    }
    if not files:
        raise SystemExit(f"Fern wrote no Python sources to {FERN_OUTPUT}")
    return files


def _referenced(schemas: dict[str, Any], node: object, found: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[1]
            if name not in found:
                found.add(name)
                _referenced(schemas, schemas[name], found)
        for value in node.values():
            _referenced(schemas, value, found)
    elif isinstance(node, list):
        for value in node:
            _referenced(schemas, value, found)


def authoring_document(openapi: dict[str, Any]) -> dict[str, Any]:
    """The OpenAPI document reduced to the authoring schemas and everything they reference."""
    schemas: dict[str, Any] = openapi["components"]["schemas"]
    found: set[str] = set()
    for root in AUTHORING_ROOTS:
        if root not in schemas:
            raise SystemExit(f"{root} is not in the OpenAPI document")
        found.add(root)
        _referenced(schemas, schemas[root], found)
    return {
        "openapi": openapi["openapi"],
        "info": openapi["info"],
        "paths": {},
        "components": {"schemas": {name: schemas[name] for name in sorted(found)}},
    }


def _render_authoring() -> bytes:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from generate_python_client_models import CODEGEN_OPTIONS

    document = authoring_document(json.loads(OPENAPI.read_text(encoding="utf-8")))
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "openapi.json"
        source.write_text(json.dumps(document, indent=2), encoding="utf-8")
        output = Path(tmp) / AUTHORING_MODULE
        subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-W",
                "ignore::FutureWarning",
                "-m",
                "datamodel_code_generator",
                *CODEGEN_OPTIONS,
                "--input",
                str(source),
                "--output",
                str(output),
            ],
            cwd=tmp,
            check=True,
        )
        return output.read_bytes()


def render() -> dict[str, bytes]:
    files = _run_fern()
    if AUTHORING_MODULE in files:
        raise SystemExit(f"Fern generated {AUTHORING_MODULE}; rename the authoring module")
    files[AUTHORING_MODULE] = _render_authoring()
    return files


def write(files: dict[str, bytes], target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def differences(target: Path, rendered: Path) -> list[str]:
    """Relative paths that differ between two trees, ignoring bytecode caches."""

    def tree(root: Path) -> set[str]:
        return {
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }

    expected, actual = tree(rendered), tree(target) if target.exists() else set()
    changed = sorted(expected ^ actual)
    changed += sorted(
        name
        for name in expected & actual
        if not filecmp.cmp(rendered / name, target / name, shallow=False)
    )
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when sdks/python/src/qdash/sdk/_generated differs from a fresh generation",
    )
    args = parser.parse_args()

    files = render()
    if not args.check:
        write(files, TARGET)
        return
    with tempfile.TemporaryDirectory() as tmp:
        rendered = Path(tmp) / "_generated"
        write(files, rendered)
        changed = differences(TARGET, rendered)
    if changed:
        listed = "".join(f"\n  {name}" for name in changed[:20])
        more = f"\n  ... and {len(changed) - 20} more" if len(changed) > 20 else ""
        raise SystemExit(
            f"{TARGET.relative_to(REPO_ROOT)} is stale; run: task generate-python-sdk{listed}{more}"
        )


if __name__ == "__main__":
    main()
