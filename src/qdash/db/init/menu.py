"""Menu initialization module."""

from qdash.db.init.initialize import initialize
from qdash.dbmodel.menu import MenuDocument


def init_menu(username: str, chip_id: str, backend: str) -> None:
    """Initialize menu document."""
    initialize()
    MenuDocument(
        name="OneQubitCheck",
        username=username,
        backend=backend,
        description="description",
        chip_id=chip_id,
        schedule={"parallel": [{"serial": ["28", "29"]}]},
        tasks=["CheckRabi"],
        task_details={
            "CheckRabi": {
                "username": username,
                "name": "CheckRabi",
                "description": "Task to check the Rabi oscillation.",
                "task_type": "qubit",
                "input_parameters": {
                    "time_range": {
                        "unit": "ns",
                        "value_type": "range",
                        "value": [0, 201, 4],
                        "description": "Time range for Rabi oscillation",
                    },
                    "shots": {
                        "unit": "a.u.",
                        "value_type": "int",
                        "value": 1024,
                        "description": "Number of shots for Rabi oscillation",
                    },
                    "interval": {
                        "unit": "ns",
                        "value_type": "int",
                        "value": 153600,
                        "description": "Time interval for Rabi oscillation",
                    },
                },
                "output_parameters": {
                    "rabi_amplitude": {
                        "unit": "a.u.",
                        "description": "Rabi oscillation amplitude",
                    },
                    "rabi_frequency": {
                        "unit": "GHz",
                        "description": "Rabi oscillation frequency",
                    },
                    "rabi_phase": {
                        "unit": "a.u.",
                        "description": "Rabi oscillation phase",
                    },
                    "rabi_offset": {
                        "unit": "a.u.",
                        "description": "Rabi oscillation offset",
                    },
                    "rabi_angle": {
                        "unit": "degree",
                        "description": "Rabi angle (in degree)",
                    },
                    "rabi_noise": {
                        "unit": "a.u.",
                        "description": "Rabi oscillation noise",
                    },
                    "rabi_distance": {
                        "unit": "a.u.",
                        "description": "Rabi distance",
                    },
                    "rabi_reference_phase": {
                        "unit": "a.u.",
                        "description": "Rabi reference phase",
                    },
                },
            },
        },
        notify_bool=False,
        tags=["debug"],
        system_info={},
    ).insert()
