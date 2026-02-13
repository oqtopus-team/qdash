# CreateDRAGHPIPulse

Calibrates DRAG beta and amplitude for leakage-suppressed π/2 pulse.

## What it measures

Optimal DRAG derivative coefficient for X90 gate.

## Physical principle

Same as CreateDRAGPIPulse but for half-rotation; may share beta but needs independent amplitude calibration.

## Expected curve

Leakage vs beta minimum; amplitude tuned for exact π/2 rotation.

## Evaluation criteria

Leakage <0.1%; rotation angle error <0.5°.

## Common failure patterns

- Coupled beta/amplitude landscape – need 2D optimization.
- Inherited beta from π pulse not optimal for π/2.
- Non-Gaussian pulse shape assumed incorrectly.

## Tips for improvement

- Often calibrate after CreateDRAGPIPulse and reuse beta.
- If amplitude differs significantly from π_pulse/2, suspect nonlinearity.
- Verify with AllXY or Clifford-based benchmarking.
