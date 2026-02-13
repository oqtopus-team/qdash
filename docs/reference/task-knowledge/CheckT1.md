# CheckT1

Measures T1 energy-relaxation time via exponential decay of the excited state.

## What it measures

T1 relaxation time – how long the qubit retains energy in the |1⟩ state.

## Physical principle

Prepare |1⟩, wait variable delay τ, measure P(|1⟩). Fit exponential decay exp(-τ/T1).

## Expected curve

Exponential decay from ~1 to ~0 as delay increases; single time constant T1.

## Evaluation criteria

T1 > 50 μs is acceptable; > 100 μs is excellent for fixed-frequency transmons.

## Common failure patterns

- Short T1 (<20 μs) – possible TLS coupling, dielectric loss, or Purcell decay.
- Non-exponential decay – multi-level leakage or readout-induced transitions.
- Large scatter between qubits – fabrication non-uniformity or localized defects.

## Tips for improvement

- If T1 fluctuates between runs, suspect TLS defects near the qubit frequency.
- Compare with T2_echo: if T2 ≈ 2*T1, decoherence is T1-limited.
- Check if readout power is too high (may cause residual excitation).

## Related context

- history(last_n=5)
- neighbor_qubits(frequency, t1)
