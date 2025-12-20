"""Sample test data for various test scenarios."""

from datetime import datetime, timezone
from typing import Any

# User test data
SAMPLE_USERS = {
    "valid_user": {
        "username": "test_user",
        "password": "secure_password123",
        "full_name": "Test User",
        "email": "test@example.com",
    },
    "admin_user": {
        "username": "admin",
        "password": "admin_password123",
        "full_name": "Admin User",
        "email": "admin@example.com",
    },
    "invalid_user": {
        "username": "",
        "password": "short",
        "full_name": "",
        "email": "invalid-email",
    },
}

# Chip test data
SAMPLE_CHIPS = {
    "basic_chip": {
        "chip_id": "test_chip_001",
        "name": "Basic Test Chip",
        "description": "A basic quantum chip for testing",
        "qubits": [
            {"id": 0, "frequency": 5.0, "anharmonicity": -200.0, "readout_frequency": 6.5},
            {"id": 1, "frequency": 5.1, "anharmonicity": -210.0, "readout_frequency": 6.6},
        ],
        "couplers": [{"control": 0, "target": 1, "coupling_strength": 10.0}],
        "topology": "linear",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "complex_chip": {
        "chip_id": "test_chip_complex",
        "name": "Complex Test Chip",
        "description": "A complex quantum chip with multiple qubits",
        "qubits": [
            {
                "id": i,
                "frequency": 5.0 + i * 0.1,
                "anharmonicity": -200.0 - i * 5,
                "readout_frequency": 6.5 + i * 0.1,
            }
            for i in range(5)
        ],
        "couplers": [
            {"control": i, "target": i + 1, "coupling_strength": 10.0 - i} for i in range(4)
        ],
        "topology": "linear",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
}

# Calibration test data
SAMPLE_CALIBRATIONS = {
    "basic_calibration": {
        "menu_name": "basic_calibration",
        "chip_id": "test_chip_001",
        "parameters": {
            "frequency_range": [4.5, 5.5],
            "power_range": [-20, 0],
            "iterations": 1000,
            "measurement_time": 1.0,
        },
        "description": "Basic calibration routine",
        "estimated_duration": 300,  # 5 minutes
    },
    "advanced_calibration": {
        "menu_name": "advanced_calibration",
        "chip_id": "test_chip_complex",
        "parameters": {
            "frequency_range": [4.0, 6.0],
            "power_range": [-30, 10],
            "iterations": 5000,
            "measurement_time": 2.0,
            "optimization_method": "gradient_descent",
        },
        "description": "Advanced calibration with optimization",
        "estimated_duration": 1800,  # 30 minutes
    },
}

# Execution test data
SAMPLE_EXECUTIONS = {
    "running_execution": {
        "execution_id": "exec_001",
        "chip_id": "test_chip_001",
        "menu_name": "basic_calibration",
        "status": "running",
        "progress": 45,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "parameters": SAMPLE_CALIBRATIONS["basic_calibration"]["parameters"],
        "current_step": "frequency_sweep",
        "estimated_completion": datetime.now(timezone.utc).isoformat(),
    },
    "completed_execution": {
        "execution_id": "exec_002",
        "chip_id": "test_chip_001",
        "menu_name": "basic_calibration",
        "status": "completed",
        "progress": 100,
        "started_at": "2024-01-01T10:00:00Z",
        "completed_at": "2024-01-01T10:05:00Z",
        "parameters": SAMPLE_CALIBRATIONS["basic_calibration"]["parameters"],
        "results": {
            "fidelity": 0.95,
            "gate_time": 20.0,
            "coherence_time": 100.0,
            "frequency_optimal": 5.05,
            "power_optimal": -15,
        },
    },
    "failed_execution": {
        "execution_id": "exec_003",
        "chip_id": "test_chip_001",
        "menu_name": "basic_calibration",
        "status": "failed",
        "progress": 23,
        "started_at": "2024-01-01T11:00:00Z",
        "failed_at": "2024-01-01T11:02:00Z",
        "parameters": SAMPLE_CALIBRATIONS["basic_calibration"]["parameters"],
        "error": {
            "code": "HARDWARE_ERROR",
            "message": "Quantum device connection lost",
            "details": "Unable to communicate with qubit control system",
        },
    },
}

# Menu test data
SAMPLE_MENUS = {
    "basic_menu": {
        "name": "basic_calibration",
        "display_name": "Basic Calibration",
        "description": "Basic single-qubit calibration routine",
        "category": "calibration",
        "parameters": [
            {
                "name": "frequency_range",
                "type": "array",
                "description": "Frequency sweep range in GHz",
                "default": [4.5, 5.5],
                "constraints": {"min_length": 2, "max_length": 2, "item_type": "float"},
            },
            {
                "name": "iterations",
                "type": "integer",
                "description": "Number of measurement iterations",
                "default": 1000,
                "constraints": {"minimum": 100, "maximum": 10000},
            },
        ],
        "estimated_duration": 300,
        "compatibility": ["single_qubit", "multi_qubit"],
    }
}

# Task test data
SAMPLE_TASKS = {
    "calibration_task": {
        "task_id": "task_001",
        "name": "Qubit Frequency Calibration",
        "description": "Calibrate qubit transition frequency",
        "type": "calibration",
        "parameters": {
            "qubit_id": 0,
            "frequency_range": [4.9, 5.1],
            "step_size": 0.001,
            "measurement_count": 100,
        },
        "dependencies": [],
        "estimated_duration": 120,
    },
    "characterization_task": {
        "task_id": "task_002",
        "name": "T1 Measurement",
        "description": "Measure qubit relaxation time T1",
        "type": "characterization",
        "parameters": {
            "qubit_id": 0,
            "delay_times": list(range(0, 200, 10)),
            "measurement_count": 1000,
        },
        "dependencies": ["task_001"],
        "estimated_duration": 300,
    },
}

# Error response test data
SAMPLE_ERROR_RESPONSES = {
    "validation_error": {
        "detail": [
            {"loc": ["body", "chip_id"], "msg": "field required", "type": "value_error.missing"}
        ]
    },
    "not_found_error": {"detail": "Resource not found"},
    "permission_error": {"detail": "Permission denied"},
    "rate_limit_error": {"detail": "Rate limit exceeded"},
}


def get_sample_data(category: str, key: str) -> dict[str, Any]:
    """Get sample data by category and key."""
    data_maps: dict[str, dict[str, Any]] = {
        "users": SAMPLE_USERS,
        "chips": SAMPLE_CHIPS,
        "calibrations": SAMPLE_CALIBRATIONS,
        "executions": SAMPLE_EXECUTIONS,
        "menus": SAMPLE_MENUS,
        "tasks": SAMPLE_TASKS,
        "errors": SAMPLE_ERROR_RESPONSES,
    }

    if category not in data_maps:
        raise ValueError(f"Unknown category: {category}")

    if key not in data_maps[category]:
        raise ValueError(f"Unknown key '{key}' in category '{category}'")

    return data_maps[category][key].copy()


def get_all_sample_data(category: str) -> dict[str, Any]:
    """Get all sample data for a category."""
    data_maps: dict[str, dict[str, Any]] = {
        "users": SAMPLE_USERS,
        "chips": SAMPLE_CHIPS,
        "calibrations": SAMPLE_CALIBRATIONS,
        "executions": SAMPLE_EXECUTIONS,
        "menus": SAMPLE_MENUS,
        "tasks": SAMPLE_TASKS,
        "errors": SAMPLE_ERROR_RESPONSES,
    }

    if category not in data_maps:
        raise ValueError(f"Unknown category: {category}")

    return {k: v.copy() for k, v in data_maps[category].items()}
