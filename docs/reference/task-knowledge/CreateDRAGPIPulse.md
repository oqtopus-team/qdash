# CreateDRAGPIPulse

Calibrates DRAG beta and amplitude for leakage-suppressed π pulse.

## What it measures

Optimal DRAG derivative coefficient (beta) for X180 gate.

## Physical principle

Scan DRAG beta parameter while monitoring leakage to |2⟩; find the minimum leakage point. Amplitude scan refines the rotation angle.

## Expected curve

Leakage vs beta shows a minimum; amplitude scan gives exact π rotation.

## Evaluation criteria

Leakage <0.1% at optimal beta; amplitude gives exact π rotation.

## Common failure patterns

- Flat leakage landscape – anharmonicity too large or pulse too slow for DRAG to matter.
- Multiple local minima – coarse scan range needed.
- Pulse distortion from AWG – DRAG waveform not faithfully reproduced.

## Tips for improvement

- Start with beta ≈ anharmonicity^(-1) as initial guess.
- Ensure pulse bandwidth is within DAC/AWG limits.
- Run after anharmonicity measurement for accurate initial parameters.
