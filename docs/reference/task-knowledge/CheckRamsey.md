# CheckRamsey

Measures T2* (free-induction) dephasing time and fine-tunes qubit frequency via Ramsey fringes.

## What it measures

T2* dephasing time and residual detuning from the drive frequency.

## Physical principle

X/2 – free evolution τ – X/2 (or Y/2), then measure. Fringes oscillate at the detuning Δf; envelope decays as exp(-τ/T2*).

## Expected curve

Damped cosine: oscillation frequency = detuning Δf, decay constant = T2*. If Δf=0, monotonic decay.

## Evaluation criteria

T2* > 20 μs acceptable; > 40 μs excellent. T2* ≤ T2_echo always.

## Common failure patterns

- T2* << T2_echo – dominated by low-frequency noise (1/f flux noise, charge noise).
- No visible fringes – detuning too small or T2* extremely short.
- Fringe frequency drift – qubit frequency unstable (TLS, thermal).

## Tips for improvement

- Ramsey with artificial detuning (Δf ~ 1–5 MHz) gives clearer fringes for fitting.
- Second-axis (Y/2) Ramsey separates detuning direction (positive vs negative).
- If T2* improves dramatically with echo, the dominant noise is low-frequency and potentially fixable.

## Related context

- history(last_n=5)
- neighbor_qubits(frequency)
