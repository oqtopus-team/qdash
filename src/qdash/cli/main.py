"""Main module for qdash CLI."""

import typer
from qdash.db.init import (
    init_chip_document,
    init_menu,
    init_task_document,
)
from qdash.db.init.initialize import initialize
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


if __name__ == "__main__":
    app()
