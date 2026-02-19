# CheckQubitFrequency

Measures qubit transition frequency via Ramsey-based detuning calibration.

## What it measures

Qubit |0⟩→|1⟩ transition frequency with high precision.

## Physical principle

Sweep drive detuning and pulse duration to map Ramsey fringes; the zero-detuning point gives the exact qubit frequency.

## Expected result

Ramsey fringes at various detunings; the frequency calibration converges when detuning is zero.

- result_type: oscillation
- x_axis: Drive detuning (MHz)
- y_axis: P(|1⟩)
- good_visual: clear Ramsey fringes with well-defined zero-detuning convergence point

## Evaluation criteria

Frequency should be reproducible across runs and within expected range of design target. Calibration should converge cleanly.

- check_questions:
  - "Is the frequency within the expected range for this qubit?"
  - "Is the frequency reproducible across repeated measurements?"
  - "Is the frequency well-separated from neighbor qubits (>100 MHz)?"

## Input parameters

None.

## Output parameters

- qubit_frequency: Qubit frequency (GHz)

## Run parameters

- detuning_range: Detuning range (GHz)
- time_range: Time range (ns)
- shots: Number of shots (a.u.)
- interval: Time interval (ns)

## Common failure patterns

- [critical] Frequency collision with neighbor (<100 MHz separation)
  - cause: fabrication deviation from design, insufficient detuning margin
  - visual: crosstalk artifacts in Ramsey fringes
  - next: assess crosstalk risk, consider frequency tuning if possible
- [warning] TLS-induced shift
  - cause: frequency jumps between runs due to TLS defects
  - visual: inconsistent frequency across repeated measurements
  - next: monitor for TLS switching, check frequency stability over time
- [warning] Large drift over time
  - cause: junction aging or thermal instability
  - visual: systematic frequency trend in history
  - next: monitor thermal stability, check junction parameters

## Tips for improvement

- Compare measured frequency with chip design values to flag fabrication outliers.
- If frequency fluctuates between runs, suspect TLS defects near qubit frequency.
- Check neighbor qubit frequencies for collision risk.

## Analysis guide

1. Compare the measured frequency with the design target value.
2. Check separation from neighbor qubit frequencies (should be >100 MHz).
3. Review frequency history for drift or instability.
4. If frequency has shifted significantly, assess impact on gate calibrations.

## Prerequisites

- CheckReadoutFrequency

## Related context

- history(last_n=5)
- neighbor_qubits(frequency)
