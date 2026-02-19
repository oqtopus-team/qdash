#!/usr/bin/env python3
"""Fetch representative calibration figures and place them in docs.

Queries MongoDB for the latest successful task results with figures,
then copies the figure files into each task's directory under
``docs/task-knowledge/<TaskName>/`` and inserts image
references into the corresponding ``index.md`` files.

Usage:
    # Copy from calib_data directory (run inside Docker or where data is mounted)
    uv run scripts/fetch_task_figures.py --calib-dir /app/calib_data

    # Fetch via API endpoint (when API server is running)
    uv run scripts/fetch_task_figures.py --api-url http://localhost:8080/api

    # Regenerate PNG from Plotly JSON
    uv run scripts/fetch_task_figures.py --calib-dir /app/calib_data --from-json
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
MD_DIR = REPO_ROOT / "docs" / "task-knowledge"

# Image reference pattern already in MD files (./filename.png within task dirs)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\./[^)]+\.png\)")


def _build_default_mongodb_uri() -> str:
    """Build MongoDB URI from .env variables.

    Uses MONGO_HOST, MONGO_PORT, MONGO_INITDB_ROOT_USERNAME, and
    MONGO_INITDB_ROOT_PASSWORD from the environment (loaded from .env).
    """
    user = os.environ.get("MONGO_INITDB_ROOT_USERNAME", "root")
    password = os.environ.get("MONGO_INITDB_ROOT_PASSWORD", "example")
    port = os.environ.get("MONGO_PORT", "27017")
    host = os.environ.get("MONGO_HOST", "localhost")
    return f"mongodb://{user}:{password}@{host}:{port}/"


def _get_mongo_client(uri: str):
    """Create a pymongo client."""
    try:
        from pymongo import MongoClient
    except ImportError:
        print("ERROR: pymongo is required. Install with: pip install pymongo", file=sys.stderr)
        sys.exit(1)
    return MongoClient(uri)


def _query_latest_figures(uri: str) -> dict[str, dict]:
    """Query MongoDB for the latest completed task results with figures.

    Returns a dict mapping task name to {figure_path, json_figure_path}.
    """
    client = _get_mongo_client(uri)
    db = client["qdash"]
    collection = db["task_result_history"]

    pipeline = [
        {"$match": {"status": "completed", "figure_path": {"$ne": []}}},
        {"$sort": {"start_at": -1}},
        {
            "$group": {
                "_id": "$name",
                "figure_path": {"$first": "$figure_path"},
                "json_figure_path": {"$first": "$json_figure_path"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    results = {}
    for doc in collection.aggregate(pipeline):
        results[doc["_id"]] = {
            "figure_path": doc.get("figure_path", []),
            "json_figure_path": doc.get("json_figure_path", []),
        }
    return results


def _copy_from_calib_dir(
    task_figures: dict[str, dict],
    *,
    from_json: bool = False,
) -> dict[str, list[str]]:
    """Copy figure files from calib_data paths to docs/figures/.

    Returns a dict mapping task name to list of copied filenames.
    """
    copied: dict[str, list[str]] = {}

    for task_name, paths in task_figures.items():
        png_paths = paths["figure_path"]
        json_paths = paths.get("json_figure_path", [])

        task_dir = MD_DIR / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        task_files: list[str] = []

        for i, png_path in enumerate(png_paths):
            src = Path(png_path)
            dest_name = f"{task_name}_{i}.png"
            dest = task_dir / dest_name

            if from_json and i < len(json_paths):
                # Regenerate PNG from Plotly JSON
                json_src = Path(json_paths[i])
                if json_src.exists():
                    _plotly_json_to_png(json_src, dest)
                    task_files.append(dest_name)
                    print(f"  Generated {dest_name} from JSON")
                    continue

            if src.exists():
                shutil.copy2(src, dest)
                task_files.append(dest_name)
                print(f"  Copied {dest_name}")
            else:
                print(f"  SKIP {dest_name}: source not found ({src})")

        # Also copy JSON files for interactive Plotly display
        for i, json_path in enumerate(json_paths):
            src = Path(json_path)
            json_dest_name = f"{task_name}_{i}.json"
            json_dest = task_dir / json_dest_name
            if src.exists():
                shutil.copy2(src, json_dest)
                print(f"  Copied {json_dest_name}")

        if task_files:
            copied[task_name] = task_files

    return copied


def _fetch_from_api(
    task_figures: dict[str, dict],
    api_url: str,
) -> dict[str, list[str]]:
    """Fetch figure files via the API endpoint.

    Returns a dict mapping task name to list of saved filenames.
    """
    try:
        import requests
    except ImportError:
        print("ERROR: requests is required. Install with: pip install requests", file=sys.stderr)
        sys.exit(1)

    fetched: dict[str, list[str]] = {}

    for task_name, paths in task_figures.items():
        png_paths = paths["figure_path"]

        task_dir = MD_DIR / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        task_files: list[str] = []

        for i, png_path in enumerate(png_paths):
            dest_name = f"{task_name}_{i}.png"
            dest = task_dir / dest_name

            url = f"{api_url.rstrip('/')}/executions/figure"
            resp = requests.get(url, params={"path": png_path}, timeout=30)
            if resp.status_code == 200:
                dest.write_bytes(resp.content)
                task_files.append(dest_name)
                print(f"  Fetched {dest_name}")
            else:
                print(f"  SKIP {dest_name}: API returned {resp.status_code}")

        if task_files:
            fetched[task_name] = task_files

    return fetched


def _plotly_json_to_png(json_path: Path, png_path: Path) -> None:
    """Convert a Plotly JSON file to a static PNG image."""
    import json

    try:
        import plotly.io as pio
    except ImportError:
        print("ERROR: plotly and kaleido are required for --from-json", file=sys.stderr)
        sys.exit(1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    fig = pio.from_json(json.dumps(data))
    fig.write_image(str(png_path), width=800, height=500, scale=2)


def _update_md_files(copied: dict[str, list[str]]) -> int:
    """Insert image references into MD files' Expected result sections.

    Returns the number of MD files updated.
    """
    updated = 0

    for task_name, filenames in copied.items():
        md_path = MD_DIR / task_name / "index.md"
        if not md_path.exists():
            print(f"  SKIP MD update: {task_name}/index.md not found")
            continue

        content = md_path.read_text(encoding="utf-8")

        # Remove any existing figure references in Expected result
        content = _IMAGE_RE.sub("", content)

        # Build image references
        img_lines = []
        for fname in filenames:
            alt = f"Example result for {task_name}"
            img_lines.append(f"![{alt}](./{fname})")

        img_block = "\n".join(img_lines)

        # Find "## Expected result" section and insert images at its end
        # (before the next ## heading)
        lines = content.splitlines()
        insert_idx = None
        in_expected = False
        for i, line in enumerate(lines):
            if line.startswith("## Expected result") or line.startswith("## Expected curve") or line.startswith("## Expected graph"):
                in_expected = True
                continue
            if in_expected and line.startswith("## "):
                # Insert before this next section
                insert_idx = i
                break
        if in_expected and insert_idx is None:
            # Expected result is the last section
            insert_idx = len(lines)

        if insert_idx is not None:
            # Remove trailing blank lines before insert point
            while insert_idx > 0 and lines[insert_idx - 1].strip() == "":
                insert_idx -= 1

            new_lines = lines[:insert_idx] + ["", *img_lines, ""] + lines[insert_idx:]
            # Clean up multiple consecutive blank lines
            cleaned: list[str] = []
            prev_blank = False
            for line in new_lines:
                is_blank = line.strip() == ""
                if is_blank and prev_blank:
                    continue
                cleaned.append(line)
                prev_blank = is_blank

            md_path.write_text("\n".join(cleaned), encoding="utf-8")
            print(f"  Updated {task_name}.md with {len(filenames)} image(s)")
            updated += 1
        else:
            print(f"  SKIP MD update: no Expected result section in {task_name}.md")

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch task reference figures for docs")
    parser.add_argument(
        "--calib-dir",
        help="Path to calib_data directory (for direct file copy)",
    )
    parser.add_argument(
        "--api-url",
        help="API base URL (e.g. http://localhost:8080/api)",
    )
    parser.add_argument(
        "--from-json",
        action="store_true",
        help="Regenerate PNG from Plotly JSON files",
    )
    parser.add_argument(
        "--mongodb-uri",
        default=None,
        help="MongoDB connection URI (default: built from .env)",
    )
    parser.add_argument(
        "--update-md",
        action="store_true",
        default=True,
        help="Update MD files with image references (default: True)",
    )
    parser.add_argument(
        "--no-update-md",
        action="store_false",
        dest="update_md",
        help="Skip updating MD files",
    )
    args = parser.parse_args()

    if not args.calib_dir and not args.api_url:
        print("ERROR: Either --calib-dir or --api-url is required", file=sys.stderr)
        return 1

    print("Querying MongoDB for latest task figures...")
    uri = args.mongodb_uri or _build_default_mongodb_uri()
    task_figures = _query_latest_figures(uri)
    print(f"Found {len(task_figures)} tasks with figures\n")

    if args.api_url:
        print(f"Fetching figures from API: {args.api_url}")
        copied = _fetch_from_api(task_figures, args.api_url)
    else:
        print(f"Copying figures from: {args.calib_dir}")
        copied = _copy_from_calib_dir(task_figures, from_json=args.from_json)

    print(f"\nPlaced {sum(len(v) for v in copied.values())} figures for {len(copied)} tasks")

    if args.update_md and copied:
        print("\nUpdating Markdown files...")
        n = _update_md_files(copied)
        print(f"Updated {n} MD files")

    return 0


if __name__ == "__main__":
    sys.exit(main())
