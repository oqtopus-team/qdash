from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "generate_task_knowledge.py"
SPEC = importlib.util.spec_from_file_location("generate_task_knowledge", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generate_task_knowledge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_task_knowledge)


def _write_index(task_dir: Path) -> Path:
    index_path = task_dir / "index.md"
    index_path.write_text(
        "# CheckExample\n\n"
        "Summary.\n\n"
        "## Evaluation criteria\n\n"
        "- The output is readable.\n",
        encoding="utf-8",
    )
    return index_path


def test_parse_markdown_file_reads_review_md(tmp_path: Path) -> None:
    task_dir = tmp_path / "category" / "CheckExample"
    task_dir.mkdir(parents=True)
    index_path = _write_index(task_dir)
    (task_dir / "review.md").write_text("# AI review guide\n", encoding="utf-8")

    parsed = generate_task_knowledge._parse_markdown_file(index_path)

    assert parsed is not None
    assert parsed["review_markdown"] == "# AI review guide\n"


def test_parse_markdown_file_without_review_md_has_empty_review_markdown(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "category" / "CheckExample"
    task_dir.mkdir(parents=True)
    index_path = _write_index(task_dir)

    parsed = generate_task_knowledge._parse_markdown_file(index_path)

    assert parsed is not None
    assert parsed["review_markdown"] == ""
