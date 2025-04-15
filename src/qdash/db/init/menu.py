"""Menu initialization module."""

from qdash.db.init.initialize import initialize
from qdash.dbmodel.menu import MenuDocument


def init_menu(username: str) -> None:
    """Initialize menu document."""
    initialize()
    MenuDocument(
        name="OneQubitCheck",
        username=username,
        description="description",
        schedule={"parallel": [{"serial": ["28", "29"]}]},
        tasks=["CheckStatus", "DumpBox", "CheckNoise", "CheckRabi"],
        task_details={
            "CheckStatus": {
                "username": username,
                "name": "CheckStatus",
                "description": "Task to check the status of the qubit.",
                "task_type": "qubit",
                "input_parameters": {},
                "output_parameters": {
                    "status": {
                        "unit": "a.u.",
                        "description": "Qubit status",
                    },
                },
            },
            "DumpBox": {
                "username": username,
                "name": "DumpBox",
                "description": "Task to dump the box.",
                "task_type": "qubit",
                "input_parameters": {},
                "output_parameters": {
                    "box": {
                        "unit": "a.u.",
                        "description": "Box",
                    },
                },
            },
            "CheckNoise": {
                "username": username,
                "name": "CheckNoise",
                "description": "Task to check the noise.",
                "task_type": "qubit",
                "input_parameters": {},
                "output_parameters": {
                    "noise": {
                        "unit": "a.u.",
                        "description": "Noise",
                    },
                },
            },
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
                },
            },
        },
        notify_bool=False,
        tags=["debug"],
        system_info={},
    ).insert()
