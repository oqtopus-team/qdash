# CheckQubitFrequency

Measures qubit transition frequency via Ramsey-based detuning calibration.

## What it measures

Qubit |0⟩→|1⟩ transition frequency with high precision.

## Physical principle

Sweep drive detuning and pulse duration to map Ramsey fringes; the zero-detuning point gives the exact qubit frequency.

## Expected curve

Ramsey fringes at various detunings; the frequency calibration converges when detuning is zero.

## Evaluation criteria

Frequency within ±50 MHz of design target; reproducible across runs.

## Common failure patterns

- Frequency collision with neighbor (<100 MHz separation) – crosstalk risk.
- TLS-induced shift – frequency jumps between runs.
- Large drift over time – indicates junction aging or thermal instability.

## Tips for improvement

- Compare measured frequency with chip design values to flag fabrication outliers.
- If frequency fluctuates between runs, suspect TLS defects near qubit frequency.
- Check neighbor qubit frequencies for collision risk.
