import logging
from datetime import datetime
from typing import cast

import pendulum
from pendulum import DateTime
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.coupling_history import CouplingHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.qubit_history import QubitHistoryDocument
from rich.console import Console
from rich.progress import track

logging.basicConfig(level=logging.INFO)


def migrate_history_dates() -> None:
    """Migrate recorded_date format in history collections.

    This function processes all documents in the history collections
    (chip_history, coupling_history, qubit_history) to ensure their
    recorded_date fields are in the correct YYYYMMDD format.
    """
    try:
        console = Console()
        console.print("[bold blue]Starting history date migration...[/]")

        initialize()
        collections = [
            ("Chip History", ChipHistoryDocument),
            ("Coupling History", CouplingHistoryDocument),
            ("Qubit History", QubitHistoryDocument),
        ]

        for collection_name, document_class in collections:
            console.print(f"\n[bold green]Migrating {collection_name}...[/]")

            # Get all documents
            documents = document_class.find_all().run()

            # Process each document with progress tracking
            for doc in track(documents, description=f"Processing {collection_name}"):
                recorded_date = doc.recorded_date
                try:
                    # Try to parse the date and convert to YYYYMMDD format
                    if len(recorded_date) == 8 and recorded_date.isdigit():
                        # Already in YYYYMMDD format - verify it's valid
                        datetime.strptime(recorded_date, "%Y%m%d")
                        new_date = recorded_date  # Keep as is since it's valid
                    else:
                        # Try to parse the date using pendulum's flexible parser
                        parsed = pendulum.parse(recorded_date)
                        # Cast the result to DateTime to handle type checking
                        date_obj = cast(DateTime, parsed)
                        # Convert to Asia/Tokyo timezone and format as YYYYMMDD
                        new_date = date_obj.in_timezone("Asia/Tokyo").format("YYYYMMDD")

                    if new_date != recorded_date:
                        console.print(f"[yellow]Converting date format: {recorded_date} -> {new_date}[/]")
                        doc.recorded_date = new_date
                        doc.save()
                        console.print(f"[green]Successfully updated document with new date: {new_date}[/]")
                    else:
                        console.print(f"[blue]Date already in correct format: {recorded_date}[/]")

                except (ValueError, TypeError) as e:
                    console.print(f"[red]Error parsing date: {recorded_date} - {e!s}[/]")
                except Exception as e:
                    console.print(f"[red]Error processing document: {e}[/]")

        console.print("\n[bold blue]Migration completed successfully![/]")
    except Exception as e:
        console.print(f"[bold red]Error during history date migration: {e}[/]")
        raise


def migrate_execution_counter_v1(
    username: str = "admin",
    chip_id: str = "64Q",
) -> None:
    """Migrate execution counter documents to include username and chip_id fields.

    This function updates all existing execution counter documents to include
    the new username and chip_id fields. For existing documents, it sets these
    fields to the provided default values.

    Args:
    ----
        username (str): The default username to set for existing documents
        chip_id (str): The default chip ID to set for existing documents

    """
    try:
        initialize()
        # Get the MongoDB collection directly
        collection = ExecutionCounterDocument.get_motor_collection()
        # Update all documents to add the new fields
        result = collection.update_many(
            filter={},  # Match all documents
            update={
                "$set": {
                    "username": username,
                    "chip_id": chip_id,
                }
            },
        )
        logging.info(
            f"Updated {result.modified_count} execution counter documents with "
            f"username: {username}, chip_id: {chip_id}"
        )
        logging.info("Execution counter migration completed successfully")
    except Exception as e:
        logging.error(f"Error during execution counter migration: {e}")
        raise
