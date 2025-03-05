from pydantic import BaseModel


class ServiceStatusResponse(BaseModel):
    """
    Represents the response for the service status.

    Attributes:
        status (str): The status of the service.
        backend (str): The backend used by the service.
        qubit_num (int): The number of qubits.
        qubit_index (str): The index of the qubit.
    """

    status: str
    backend: str
    qubit_num: int
    qubit_index: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "available",
                    "backend": "Simulator",
                    "qubit_num": 4,
                    "qubit_index": "1,2,3,5",
                }
            ]
        }
    }


class ServiceStatusRequest(BaseModel):
    """
    Represents a request to get the status of a service.

    Attributes:
        status (str): The status of the service.
        backend (str): The backend of the service.
        qubit_num (int): The number of qubits in the service.
        qubit_index (str): The index of the qubit in the service.
    """

    status: str
    backend: str
    qubit_num: int
    qubit_index: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "available",
                    "backend": "Simulator",
                    "qubit_num": 4,
                    "qubit_index": "1,2,3,5",
                }
            ]
        }
    }


class RestartServiceResponse(BaseModel):
    """
    Represents the response for restarting a service.

    Attributes:
        message (str): The message indicating the success of the restart.
    """

    message: str = "QMT server restarted"

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "QMT server restarted",
                }
            ]
        }
    }


class UpdateTopologyInfoResponse(BaseModel):
    """
    Represents the response for updating the topology information.

    Attributes:
        message (str): The message indicating the success of the update.
    """

    message: str = "Topology information updated"

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Topology information updated",
                }
            ]
        }
    }


class UpdateWiringInfoResponse(BaseModel):
    """
    Represents the response for updating the wiring information.

    Attributes:
        message (str): The message indicating the success of the update.
    """

    message: str = "Wiring information updated"

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Wiring information updated",
                }
            ]
        }
    }


class ScheduleResponse(BaseModel):
    idx: int
    name: str
    description: str
    cron: str
    timezone: str
    active: bool
    scheduled: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "idx": 1,
                    "name": "schedule",
                    "description": "schedule description",
                    "cron": "0 0 * * *",
                    "timezone": "UTC",
                    "active": True,
                    "scheduled": "2022-01-01 00:00:00",
                }
            ]
        }
    }


class ScheduleRequest(BaseModel):
    idx: int
    cron: str
    active: bool

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "idx": 1,
                    "cron": "0 0 * * *",
                    "active": True,
                }
            ]
        }
    }
