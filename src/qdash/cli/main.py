"""Main module for qdash CLI."""

import typer
from qdash.db.init import (
    init_chip_document,
    init_menu,
    init_task_document,
)
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.parameter import ParameterDocument

app = typer.Typer(
    name="qdash",
    help="Command line interface for qdash",
    add_completion=True,
)


@app.command()
def version() -> None:
    """Show qdash version."""
    from qdash import __version__

    typer.echo(f"qdash version: {__version__}")


@app.command()
def add_new_chip(
    username: str = typer.Option(..., "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option(..., "--chip-id", "-c", help="Chip ID for initialization"),
    size: int = typer.Option(..., "--size", "-s", help="Size of the chip (e.g., 64, 144)"),
) -> None:
    """Add new chip."""
    typer.echo(f"Adding new chip with ID: {chip_id} for user: {username} with size: {size}")
    if not typer.confirm("Do you want to proceed?"):
        typer.echo("Chip addition cancelled.")
        typer.echo("No changes made to the database.")
        typer.echo("Exiting without changes.")
        raise typer.Exit(0)
    try:
        from qdash.db.init.chip import init_chip_document

        init_chip_document(username=username, chip_id=chip_id, size=size)
        typer.echo(f"New chip added successfully (username: {username}, chip_id: {chip_id}, size: {size})")
    except Exception as e:
        typer.echo(f"Error adding new chip: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def update_active_output_parameters(
    username: str = typer.Option(..., "--username", "-u", help="Username for initialization"),
) -> None:
    """Update active output parameters."""
    typer.echo(f"Updating active output parameters for username: {username}")
    if not typer.confirm("Do you want to proceed?"):
        typer.echo("Update cancelled.")
        typer.echo("No changes made to active output parameters.")
        typer.echo("Exiting without changes.")
        raise typer.Exit(0)
    try:
        from qdash.cli.add import update_active_output_parameters

        params = update_active_output_parameters(username=username)
        initialize()
        ParameterDocument.insert_parameters(params, username=username)
        typer.echo(f"Active output parameters updated successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error updating active output parameters: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def update_active_tasks(
    username: str = typer.Option(..., "--username", "-u", help="Username for initialization"),
    backend: str = typer.Option(..., "--backend", "-b", help="Backend for task initialization"),
) -> None:
    """Update active tasks."""
    typer.echo(f"Updating active tasks for username: {username} and backend: {backend}")
    if not typer.confirm("Do you want to proceed?"):
        typer.echo("Update cancelled.")
        typer.echo("No changes made to active tasks.")
        typer.echo("Exiting without changes.")
        raise typer.Exit(0)
    try:
        init_task_document(username=username, backend=backend)
        typer.echo(f"Active tasks updated successfully (username: {username})")
        typer.echo(f"Backend: {backend}")
    except Exception as e:
        typer.echo(f"Error updating active tasks: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def init_all_data(
    username: str = typer.Option(..., "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option(..., "--chip-id", "-c", help="Chip ID for initialization"),
    chip_size: int = typer.Option(..., "--chip-size", "-s", help="Size of the chip (e.g., 64, 144)"),
    backend: str = typer.Option(..., "--backend", "-b", help="Backend (e.g., qubex)"),
) -> None:
    """Initialize all data with confirmation."""
    typer.echo("⚠️  You are about to initialize all data with the following settings:")
    typer.echo(f"   Username  : {username}")
    typer.echo(f"   Chip ID   : {chip_id}")
    typer.echo(f"   Chip Size : {chip_size}")
    typer.echo(f"   Backend   : {backend}")

    if not typer.confirm("Do you want to proceed?"):
        typer.echo("Initialization cancelled.")
        raise typer.Exit(0)

    try:
        typer.echo("Starting initialization...")

        init_chip_document(username=username, chip_id=chip_id, size=chip_size)
        typer.echo("✅ Chip data initialized")

        init_menu(username=username, chip_id=chip_id, backend=backend)
        typer.echo("✅ Menu data initialized")

        init_task_document(username=username, backend=backend)
        typer.echo("✅ Task data initialized")

        typer.echo("\n🎉 All data initialized successfully")
    except Exception as e:
        typer.echo(f"❌ Error during initialization: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def export_note(
    execution_id: str = typer.Option(..., "--execution-id", "-e", help="Execution ID (e.g., 20250130-001)"),
    task_id: str = typer.Option("master", "--task-id", "-t", help="Task ID (default: master)"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
    username: str = typer.Option(None, "--username", "-u", help="Username filter (optional)"),
    chip_id: str = typer.Option(None, "--chip-id", "-c", help="Chip ID filter (optional)"),
) -> None:
    """Export calibration note from MongoDB to file.

    This command retrieves a calibration note from MongoDB and exports it to a JSON file.
    Useful for debugging or archival purposes.

    Examples:
        # Export master note for execution
        qdash export-note --execution-id 20250130-001

        # Export specific task note
        qdash export-note --execution-id 20250130-001 --task-id abc-123-def

        # Export to specific file
        qdash export-note -e 20250130-001 -o /path/to/output.json

        # Filter by username
        qdash export-note -e 20250130-001 -u alice

        # Filter by chip ID
        qdash export-note -e 20250130-001 -c 64Qv3
    """
    try:
        from qdash.cli.export_note import export_calibration_note

        export_calibration_note(
            execution_id=execution_id,
            task_id=task_id,
            output=output,
            username=username,
            chip_id=chip_id,
        )
    except Exception as e:
        typer.echo(f"❌ Error exporting calibration note: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
