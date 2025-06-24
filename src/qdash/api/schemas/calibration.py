from typing import ClassVar, TypeVar

from pydantic import BaseModel
from qdash.datamodel.menu import MenuModel

T = TypeVar("T")


class ExecuteCalibRequest(MenuModel):
    """ExecuteCalibRequest is a subclass of MenuModel."""

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "CheckRabi",
                    "username": "admin",
                    "chip_id": "chip1",
                    "description": "check one qubit characteristics short",
                    "qids": [["28"]],
                    "notify_bool": False,
                    "backend": "qubex",
                    "tasks": [
                        "CheckRabi",
                    ],
                    "task_details": {
                        "CheckRabi": {
                            "username": "admin",
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
                    "tags": ["debug"],
                },
            ]
        }
    }


class ExecuteCalibResponse(BaseModel):
    """ExecuteCalibResponse is a subclass of BaseModel."""

    flow_run_url: str
    qdash_ui_url: str


class ScheduleCalibRequest(BaseModel):
    """ScheduleCalibRequest is a subclass of BaseModel."""

    menu_name: str
    scheduled: str


class ScheduleCalibResponse(BaseModel):
    """ScheduleCalibResponse is a subclass of BaseModel."""

    menu_name: str
    menu: ExecuteCalibRequest
    description: str
    note: str
    timezone: str
    scheduled_time: str
    flow_run_id: str
