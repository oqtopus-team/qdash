"""CLI command for exporting calibration notes from MongoDB to file."""

import json
from pathlib import Path

import typer
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.initialize import initialize


def export_calibration_note(
    execution_id: str,
    task_id: str = "master",
    output: str | None = None,
    username: str | None = None,
    chip_id: str | None = None,
) -> None:
    """Export calibration note from MongoDB to file.

    Args:
    ----
        execution_id: Execution ID (e.g., "20250130-001")
        task_id: Task ID to export (default: "master")
        output: Output file path (default: "{execution_id}_{task_id}.json")
        username: Username filter (optional)
        chip_id: Chip ID filter (optional)

    """
    # Initialize MongoDB connection
    initialize()

    # Build query
    query: dict[str, str] = {
        "execution_id": execution_id,
        "task_id": task_id,
    }
    if username:
        query["username"] = username
    if chip_id:
        query["chip_id"] = chip_id

    # Fetch document from MongoDB
    doc = CalibrationNoteDocument.find_one(query).run()

    if not doc:
        query_str = ", ".join(f"{k}={v}" for k, v in query.items())
        typer.echo(f"❌ No calibration note found for {query_str}", err=True)
        raise typer.Exit(1)

    # Determine output path
    if output:
        output_path = Path(output)
    else:
        output_path = Path(f"{execution_id}_{task_id}.json")

    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    output_path.write_text(json.dumps(doc.note, indent=2, ensure_ascii=False))

    typer.echo(f"✅ Exported calibration note to {output_path}")
    typer.echo(f"   Execution ID: {execution_id}")
    typer.echo(f"   Task ID: {task_id}")
    if username:
        typer.echo(f"   Username: {username}")
    if chip_id:
        typer.echo(f"   Chip ID: {chip_id}")
    typer.echo(f"   Timestamp: {doc.timestamp}")
