"""Generate the Python client's Pydantic models from the OpenAPI document."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_INPUT = Path("docs/oas/openapi.json")
DEFAULT_OUTPUT = Path("clients/python/src/qdash/client/services/models.py")

# Keep these options in one place so `task generate` and the `--check` gate agree.
CODEGEN_OPTIONS = (
    "--use-schema-description",
    "--target-python-version",
    "3.12",
    "--field-constraints",
    "--use-annotated",
    "--use-field-description",
    "--input-file-type",
    "openapi",
    "--collapse-root-models",
    "--enum-field-as-literal",
    "one",
    "--set-default-enum-member",
    "--use-union-operator",
    "--use-subclass-enum",
    "--output-model-type",
    "pydantic_v2.BaseModel",
    "--disable-timestamp",
    "--use-standard-collections",
    "--strict-nullable",
    "--use-default",
    # Pin the formatters datamodel-codegen applies before Ruff so the output stays stable when
    # its default changes.
    "--formatters",
    "black",
    "isort",
)


def render_models(openapi: Path) -> str:
    """Return the formatted models module generated from ``openapi``."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "models.py"
        subprocess.run(  # noqa: S603
            [
                sys.executable,
                # The pinned release warns about future default changes the options above pin.
                "-W",
                "ignore::FutureWarning",
                "-m",
                "datamodel_code_generator",
                *CODEGEN_OPTIONS,
                "--input",
                str(openapi),
                "--output",
                str(output),
            ],
            check=True,
        )
        generated = output.read_text(encoding="utf-8")
    # Format as the client's models file so Ruff applies the repository settings to any output.
    formatted = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", "format", "--stdin-filename", str(DEFAULT_OUTPUT), "-"],
        input=generated,
        capture_output=True,
        text=True,
        check=True,
    )
    return formatted.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the existing models differ from the OpenAPI document",
    )
    args = parser.parse_args()

    output: Path = args.output
    rendered = render_models(args.input)
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"{output} is stale; run: task generate-python-schema")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
