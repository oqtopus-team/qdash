"""Shared helpers for knowledge-draft tests: a stand-in generator and zip builders."""

from __future__ import annotations

import io
import stat
import zipfile

# Enough of the knowledge repository's generate.py for the draft store: the
# H1 check, the module-level warnings list, and examples with one figure each.
GENERATOR = """
warnings = []


def warn(message):
    warnings.append(message)


def _parse_task(task_dir, category):
    document = task_dir / "task.md"
    if not document.is_file():
        document = task_dir / "index.md"
    lines = document.read_text(encoding="utf-8").splitlines()
    title = next((line[2:].strip() for line in lines if line.startswith("# ")), None)
    if title is None:
        warn(f"{task_dir.name}: no H1 title")
        return None
    if title != task_dir.name:
        warn(f"{category}/{task_dir.name}: H1 '{title}' differs from the directory name")
    examples = []
    examples_dir = task_dir / "examples"
    for path in sorted(examples_dir.glob("*.md")) if examples_dir.is_dir() else []:
        examples.append(
            {
                "id": path.stem,
                "title": path.stem,
                "outcome": "suboptimal",
                "status": "SHORT_T1",
                "figures": [{"alt": "", "path": f"examples/{path.stem}.png"}],
                "diagnosis": path.read_text(encoding="utf-8").strip(),
            }
        )
    return {
        "name": title,
        "category": category,
        "background": "\\n".join(lines[1:]).strip(),
        "figures": [],
        "examples": examples,
    }
"""

INDEX = "# CheckRabi\n\nRabi oscillation.\n\n## Expected plot\n\nA good result: a damped cosine.\n"
PNG = b"\x89PNG\r\n\x1a\nfake"


def make_zip(files: dict[str, bytes | str], *, links: tuple[str, ...] = ()) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        for name in links:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "/etc/passwd")
    return buffer.getvalue()


RABI: dict[str, bytes | str] = {
    "CheckRabi/task.md": INDEX,
    "CheckRabi/examples/short.md": "The decay is too fast.",
    "CheckRabi/examples/short.png": PNG,
}
