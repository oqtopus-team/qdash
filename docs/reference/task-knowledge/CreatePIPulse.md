# CreatePIPulse

Calibrates π (X180) gate pulse amplitude via Rabi-based fitting.

## What it measures

Optimal pulse amplitude for a full π rotation (|0⟩ → |1⟩).

## Physical principle

Apply a shaped pulse of fixed duration and sweep amplitude; fit the Rabi oscillation to find the amplitude corresponding to exactly π rotation.

## Expected curve

Cosine-like Rabi oscillation vs amplitude; π pulse at the first minimum (population inverted).

## Evaluation criteria

Amplitude in linear regime; fit R² > 0.95; consistent with expected drive power.

## Common failure patterns

- Over/under-rotation – amplitude calibration error accumulates in gate sequences.
- Leakage to |2⟩ – if pulse is too fast relative to anharmonicity.
- Nonlinear drive response – DAC/amplifier compression at high amplitudes.

## Tips for improvement

- Duration is fixed; only amplitude is optimized. Check that duration is appropriate for anharmonicity.
- If R² is poor, the qubit frequency may have drifted – recalibrate frequency first.
- Compare π amplitude with previous runs to detect drift.
