"""Minimal Quantum Machines configuration for one qubit on an OPX (controller con1).

This is a native QUA configuration: it defines the ``config`` dictionary that
``QuantumMachinesManager.open_qm(config)`` takes, and works without QDash:

    from configuration import config

QDash executes this file as trusted Python when a qm or qm-fake backend starts and reads
``config``; it does not convert or rewrite the dictionary. Keep this module to
definitions only: anything that connects to a QOP server belongs in a separate script
or under ``if __name__ == "__main__":``, which QDash does not run.

The qubit drive and the readout resonator use IQ mixers. Frequencies are in Hz, lengths
in ns, amplitudes in V.
"""

# Qubit drive
qubit_LO = 5_000_000_000
qubit_IF = 100_000_000
x180_len = 40
x180_amp = 0.2

# Readout
resonator_LO = 6_000_000_000
resonator_IF = 50_000_000
readout_len = 200
readout_amp = 0.1
time_of_flight = 24

config = {
    "controllers": {
        "con1": {
            "analog_outputs": {
                1: {"offset": 0.0},  # qubit I
                2: {"offset": 0.0},  # qubit Q
                3: {"offset": 0.0},  # resonator I
                4: {"offset": 0.0},  # resonator Q
            },
            "digital_outputs": {},
            "analog_inputs": {
                1: {"offset": 0.0},  # I from down-conversion
                2: {"offset": 0.0},  # Q from down-conversion
            },
        },
    },
    "elements": {
        "qubit": {
            "mixInputs": {
                "I": ("con1", 1),
                "Q": ("con1", 2),
                "lo_frequency": qubit_LO,
                "mixer": "mixer_qubit",
            },
            "intermediate_frequency": qubit_IF,
            "operations": {
                "x180": "x180_pulse",
            },
        },
        "resonator": {
            "mixInputs": {
                "I": ("con1", 3),
                "Q": ("con1", 4),
                "lo_frequency": resonator_LO,
                "mixer": "mixer_resonator",
            },
            "intermediate_frequency": resonator_IF,
            "operations": {
                "readout": "readout_pulse",
            },
            "outputs": {
                "out1": ("con1", 1),
                "out2": ("con1", 2),
            },
            "time_of_flight": time_of_flight,
            "smearing": 0,
        },
    },
    "pulses": {
        "x180_pulse": {
            "operation": "control",
            "length": x180_len,
            "waveforms": {"I": "x180_wf", "Q": "zero_wf"},
        },
        "readout_pulse": {
            "operation": "measurement",
            "length": readout_len,
            "waveforms": {"I": "readout_wf", "Q": "zero_wf"},
            "integration_weights": {
                "cos": "cosine_weights",
                "sin": "sine_weights",
                "minus_sin": "minus_sine_weights",
            },
            "digital_marker": "ON",
        },
    },
    "waveforms": {
        "x180_wf": {"type": "constant", "sample": x180_amp},
        "readout_wf": {"type": "constant", "sample": readout_amp},
        "zero_wf": {"type": "constant", "sample": 0.0},
    },
    "digital_waveforms": {
        "ON": {"samples": [(1, 0)]},
    },
    "integration_weights": {
        "cosine_weights": {
            "cosine": [(1.0, readout_len)],
            "sine": [(0.0, readout_len)],
        },
        "sine_weights": {
            "cosine": [(0.0, readout_len)],
            "sine": [(1.0, readout_len)],
        },
        "minus_sine_weights": {
            "cosine": [(0.0, readout_len)],
            "sine": [(-1.0, readout_len)],
        },
    },
    "mixers": {
        "mixer_qubit": [
            {
                "intermediate_frequency": qubit_IF,
                "lo_frequency": qubit_LO,
                "correction": (1, 0, 0, 1),
            },
        ],
        "mixer_resonator": [
            {
                "intermediate_frequency": resonator_IF,
                "lo_frequency": resonator_LO,
                "correction": (1, 0, 0, 1),
            },
        ],
    },
}
