"""Temporary workspace preparation for hosted workflow authoring agents."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkflowAgentWorkspace:
    """Prepared temporary workspace for a single workflow editing job."""

    root: Path
    filename: str
    flow_path: Path
    prompt: str


def prepare_workspace(
    root: Path,
    *,
    name: str,
    code: str,
    project_id: str,
    user_prompt: str,
    context: str,
) -> WorkflowAgentWorkspace:
    """Write a temporary workflow file and instructions for an agent job."""
    filename = f"{name}.py"
    flow_path = root / filename
    flow_path.write_text(code, encoding="utf-8")
    (root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# QDash workflow editing workspace",
                "",
                "Edit only the Python workflow file requested by the user.",
                "Keep the code compatible with Prefect and QDash workflow APIs.",
                "Do not run hardware, deployments, package installs, or destructive commands.",
            ]
        ),
        encoding="utf-8",
    )

    prompt = "\n".join(
        [
            f"Edit `{filename}` for QDash project `{project_id}`.",
            "Modify the file in place. Keep the same public flow entrypoint unless the user explicitly asks for a rename.",
            "After editing, reply with a concise summary only.",
            "",
            "## User request",
            user_prompt.strip() or "(no request provided)",
            "",
            "## QDash authoring context",
            context.strip() or "(none)",
        ]
    )
    return WorkflowAgentWorkspace(root=root, filename=filename, flow_path=flow_path, prompt=prompt)


def build_unified_diff(filename: str, before: str, after: str) -> str:
    """Build a unified diff for a workflow edit."""
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )
