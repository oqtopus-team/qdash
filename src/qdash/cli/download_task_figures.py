"""CLI command for downloading task JSON figures from calibration data."""

import json
import shutil
from datetime import datetime
from pathlib import Path

import typer
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument


def download_task_figures(
    task_name: str,
    chip_id: str,
    username: str,
    output_dir: str | None = None,
) -> None:
    """Download JSON figures for tasks matching the criteria.

    This function retrieves the most recent completed task result for EACH qubit/coupling
    on the specified chip, ensuring you get the latest data for all qubits.

    Args:
    ----
        task_name: Task name to search for (e.g., "CheckResonatorSpectroscopy")
        chip_id: Chip ID to filter by
        username: Username to filter by
        output_dir: Output directory for downloaded files (default: "./downloads/{task_name}_{chip_id}")

    """
    # Initialize MongoDB connection
    initialize()

    # Build query
    query: dict[str, str] = {
        "name": task_name,
        "chip_id": chip_id,
        "username": username,
        "status": "completed",
    }

    # Fetch ALL matching documents, sorted by most recent first
    all_docs = list(
        TaskResultHistoryDocument.find(query).sort([("system_info.updated_at", -1)]).run()
    )

    if not all_docs:
        query_str = ", ".join(f"{k}={v}" for k, v in query.items())
        typer.echo(f"❌ No completed tasks found for {query_str}", err=True)
        raise typer.Exit(1)

    # Group by qid and take the most recent one for each
    qid_to_latest_task = {}
    for doc in all_docs:
        qid = doc.qid
        if qid not in qid_to_latest_task:
            qid_to_latest_task[qid] = doc

    # Convert to sorted list for consistent ordering
    docs_list = [qid_to_latest_task[qid] for qid in sorted(qid_to_latest_task.keys())]

    # Determine output directory
    if output_dir:
        output_path = Path(output_dir)
    else:
        output_path = Path(f"./downloads/{task_name}_{chip_id}")

    output_path.mkdir(parents=True, exist_ok=True)

    typer.echo(f"📁 Output directory: {output_path.absolute()}")
    typer.echo(f"🔍 Found {len(docs_list)} qubit(s) with completed tasks")
    typer.echo("📊 Downloading latest result for each qubit\n")

    # Metadata for all downloaded files
    metadata_list = []

    for task_idx, task in enumerate(docs_list, 1):
        typer.echo(f"{'='*60}")
        typer.echo(f"Task {task_idx}/{len(docs_list)}")
        typer.echo(f"{'='*60}")
        typer.echo(f"  Task ID: {task.task_id}")
        typer.echo(f"  Execution ID: {task.execution_id}")
        typer.echo(f"  Qubit/Coupling ID: {task.qid}")
        typer.echo(f"  Status: {task.status}")
        typer.echo(f"  Start: {task.start_at}")
        typer.echo(f"  End: {task.end_at}")

        if not task.json_figure_path:
            typer.echo("  ⚠️  No JSON figures available for this task")
            continue

        typer.echo(f"  📊 JSON Figures: {len(task.json_figure_path)}")

        task_metadata = {
            "task_id": task.task_id,
            "task_name": task.name,
            "execution_id": task.execution_id,
            "qid": task.qid,
            "chip_id": task.chip_id,
            "username": task.username,
            "status": task.status,
            "start_at": task.start_at,
            "end_at": task.end_at,
            "elapsed_time": task.elapsed_time,
            "input_parameters": task.input_parameters,
            "output_parameters": task.output_parameters,
            "json_figures": [],
        }

        # Download each JSON figure
        for fig_idx, json_path in enumerate(task.json_figure_path):
            # Convert /app path to /workspace path if needed
            converted_path = json_path.replace("/app/", "/workspace/qdash/")
            source_path = Path(converted_path)

            if not source_path.exists():
                typer.echo(f"    ⚠️  Figure {fig_idx + 1}: File not found - {json_path}")
                typer.echo(f"        Tried: {converted_path}")
                continue

            # Use original filename from the database path (not converted path)
            original_filename = Path(json_path).name
            dest_filename = original_filename
            dest_path = output_path / dest_filename

            # Copy file
            shutil.copy2(source_path, dest_path)
            typer.echo(f"    ✅ Figure {fig_idx + 1}: {dest_filename}")

            # Add to metadata
            task_metadata["json_figures"].append(
                {
                    "index": fig_idx,
                    "original_path": str(json_path),
                    "downloaded_filename": dest_filename,
                    "downloaded_path": str(dest_path.absolute()),
                }
            )

        metadata_list.append(task_metadata)
        typer.echo()

    # Write metadata file
    meta_path = output_path / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "query": {
                    "task_name": task_name,
                    "chip_id": chip_id,
                    "username": username,
                },
                "total_tasks": len(docs_list),
                "download_timestamp": datetime.now().isoformat(),
                "tasks": metadata_list,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    typer.echo(f"{'='*60}")
    typer.echo("✅ Download complete!")
    typer.echo(f"{'='*60}")
    typer.echo(f"📁 Files saved to: {output_path.absolute()}")
    typer.echo(f"📄 Metadata saved to: {meta_path.absolute()}")
    typer.echo(
        f"📊 Total JSON figures downloaded: {sum(len(t['json_figures']) for t in metadata_list)}"
    )
