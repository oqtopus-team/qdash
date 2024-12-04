import typer
from setup_bluefors import delete_bluefors, init_bluefors
from setup_cooling_down import delete_cooling_down, init_cooling_down
from setup_execution_lock import delete_execution_lock, init_execution_lock
from setup_menu import delete_menu, init_menu
from setup_one_qubit_calib import delete_one_qubit_calib, init_one_qubit_calib
from setup_qpu import delete_qpu, init_qpu
from setup_session_info import delete_session_info, init_session_info
from setup_two_qubit_calib import delete_two_qubit_calib, init_two_qubit_calib
from setup_wiring_info import delete_wiring_info, init_wiring_info

app = typer.Typer()


@app.command()
def init_all():
    init_qpu()
    init_wiring_info()
    init_session_info()
    init_menu()
    init_bluefors()
    init_cooling_down()
    init_execution_lock()
    init_one_qubit_calib()
    init_two_qubit_calib()
    typer.echo("Initialization completed.")


@app.command()
def teardown_all():
    delete_qpu()
    delete_wiring_info()
    delete_session_info()
    delete_menu()
    delete_bluefors()
    delete_cooling_down()
    delete_execution_lock()
    delete_one_qubit_calib()
    delete_two_qubit_calib()
    typer.echo("Teardown completed.")


if __name__ == "__main__":
    app()
