"""Main module for qdash CLI."""

import typer
from qdash.db.init import (
    init_chip_document,
    init_coupling_document,
    init_menu,
    init_qubit_document,
    init_task_document,
)
from qdash.db.init.initialize import initialize
from qdash.dbmodel.parameter import ParameterDocument

app = typer.Typer(
    name="qdash",
    help="Command line interface for qdash",
    add_completion=False,
)


@app.command()
def version() -> None:
    """Show qdash version."""
    from qdash import __version__

    typer.echo(f"qdash version: {__version__}")


@app.command()
def init_qubit_data(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
) -> None:
    """Initialize qubit data."""
    try:
        typer.echo(f"Initializing qubit data for username: {username}")
        typer.echo(f"Chip ID: {chip_id}")
        init_qubit_document(username=username, chip_id=chip_id)
        typer.echo(f"Qubit data initialized successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error initializing qubit data: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def init_coupling_data(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
) -> None:
    """Initialize coupling data."""
    try:
        typer.echo(f"Initializing coupling data for username: {username}")
        typer.echo(f"Chip ID: {chip_id}")
        init_coupling_document(username=username, chip_id=chip_id)
        typer.echo(f"Coupling data initialized successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error initializing coupling data: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def init_chip_data(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
) -> None:
    """Initialize chip data."""
    try:
        typer.echo(f"Initializing chip data for username: {username}")
        typer.echo(f"Chip ID: {chip_id}")
        init_chip_document(username=username, chip_id=chip_id)
        typer.echo(f"Chip data initialized successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error initializing chip data: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def init_menu_data(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
) -> None:
    """Initialize menu data."""
    try:
        typer.echo(f"Initializing menu data for username: {username}")
        init_menu(username=username, chip_id=chip_id)
        typer.echo(f"Menu data initialized successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error initializing menu data: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def init_task_data(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
) -> None:
    """Initialize task data."""
    try:
        typer.echo(f"Initializing task data for username: {username}")
        init_task_document(username=username)
        typer.echo(f"Task data initialized successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error initializing task data: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def migrate_v1_0_16_to_v1_0_17(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
) -> None:
    """Migrate data from v1.0.16 to v1.0.17."""
    try:
        from qdash.dbmodel.migration import migrate_v1_0_16_to_v1_0_17

        migrate_v1_0_16_to_v1_0_17(username=username, chip_id=chip_id)
        typer.echo(
            f"Data migration from v1.0.16 to v1.0.17 completed successfully (username: {username})"
        )
    except Exception as e:
        typer.echo(f"Error during migration: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def migrate_execution_counter_v1(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
) -> None:
    """Migrate execution counter documents to include username and chip_id fields."""
    try:
        from qdash.dbmodel.migration import migrate_execution_counter_v1

        migrate_execution_counter_v1(username=username, chip_id=chip_id)
        typer.echo(f"Execution counter migration completed successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error during execution counter migration: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def add_new_chip(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
    size: int = typer.Option(64, "--size", "-s", help="Size of the chip (e.g., 64, 144)"),
) -> None:
    """Add new chip."""
    try:
        from qdash.cli.add import add_new_chip

        add_new_chip(username=username, chip_id=chip_id, size=size)
        typer.echo(f"New chip added successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error adding new chip: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def rename_all_menu_with_chip_id(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
) -> None:
    """Rename menu with chip ID."""
    try:
        from qdash.cli.add import rename_all_menu_with_chip_id

        rename_all_menu_with_chip_id(username=username, chip_id=chip_id)
        typer.echo(f"Menu renamed with chip ID successfully (username: {username})")
    except Exception as e:
        typer.echo(f"Error renaming menu with chip ID: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def update_active_output_parameters(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
) -> None:
    """Update active output parameters."""
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
def migrate_dates() -> None:
    """Migrate recorded_date format in history collections."""
    try:
        from qdash.dbmodel.migration import migrate_history_dates

        migrate_history_dates()
        typer.echo("History date migration completed successfully")
    except Exception as e:
        typer.echo(f"Error during history date migration: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def update_active_tasks(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    backend: str = typer.Option("qubex", "--backend", "-b", help="Backend for task initialization"),
) -> None:
    """Update active tasks."""
    try:
        init_task_document(username=username, backend=backend)
        typer.echo(f"Active tasks updated successfully (username: {username})")
        typer.echo(f"Backend: {backend}")
    except Exception as e:
        typer.echo(f"Error updating active tasks: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def init_all_data(
    username: str = typer.Option("admin", "--username", "-u", help="Username for initialization"),
    chip_id: str = typer.Option("64Q", "--chip-id", "-c", help="Chip ID for initialization"),
) -> None:
    """Initialize all data."""
    try:
        typer.echo(f"Initializing data for username: {username}")
        typer.echo(f"Chip ID: {chip_id}")

        init_qubit_document(username=username, chip_id=chip_id)
        typer.echo("Qubit data initialized")

        init_coupling_document(username=username, chip_id=chip_id)
        typer.echo("Coupling data initialized")

        init_chip_document(username=username, chip_id=chip_id)
        typer.echo("Chip data initialized")

        init_menu(username=username, chip_id=chip_id)
        typer.echo("Menu data initialized")

        init_task_document(username=username)
        typer.echo("Task data initialized")

        typer.echo("\nAll data initialized successfully")
    except Exception as e:
        typer.echo(f"Error during initialization: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
