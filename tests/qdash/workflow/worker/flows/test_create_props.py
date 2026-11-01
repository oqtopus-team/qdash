from qdash.workflow.worker.flows.push_props.create_props import _normalize_qubit_data


def test_normalize_qubit_data_maps_legacy_anharmonicity() -> None:
    legacy = {"anharmonicity": {"value": -0.3, "unit": "GHz"}}

    normalized = _normalize_qubit_data(legacy)

    assert normalized == {"qubit_anharmonicity": legacy["anharmonicity"]}


def test_normalize_qubit_data_prefers_canonical_anharmonicity() -> None:
    canonical = {"value": -0.31, "unit": "GHz"}
    data = {
        "qubit_anharmonicity": canonical,
        "anharmonicity": {"value": -0.3, "unit": "GHz"},
    }

    normalized = _normalize_qubit_data(data)

    assert normalized == {"qubit_anharmonicity": canonical}
