"""Main module for qdash CLI."""

import typer
from qdash.db.init import (
    init_chip_document,
    init_coupling_document,
    init_menu,
    init_qubit_document,
    init_task_document,
)

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
) -> None:
    """Initialize menu data."""
    try:
        typer.echo(f"Initializing menu data for username: {username}")
        init_menu(username=username)
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

        init_menu(username=username)
        typer.echo("Menu data initialized")

        init_task_document(username=username)
        typer.echo("Task data initialized")

        typer.echo("\nAll data initialized successfully")
    except Exception as e:
        typer.echo(f"Error during initialization: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
