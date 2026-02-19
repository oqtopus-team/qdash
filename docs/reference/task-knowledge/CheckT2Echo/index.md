# CheckT2Echo

Measures T2 echo (Hahn echo) coherence time, refocusing low-frequency noise.

## What it measures

T2 echo – phase coherence time after a Hahn-echo refocusing pulse.

## Physical principle

X/2 – wait τ/2 – π – wait τ/2 – X/2, then measure. Refocuses static and slow noise, revealing intrinsic dephasing.

## Expected result

Exponential (or Gaussian) decay envelope of echo amplitude vs total delay τ.

- result_type: decay_curve
- x_axis: Total delay τ (μs)
- y_axis: Echo amplitude
- fit_model: A * exp(-(τ/T2_echo)^n) + B, n=1 or 2
- typical_range: 30–300 μs for fixed-frequency transmons
- good_visual: smooth decay envelope with clear time constant, low residuals

![T2 echo decay curve](./0.png)

## Evaluation criteria

T2_echo should satisfy T2_echo ≤ 2*T1. Compare with T2* (Ramsey) to quantify low-frequency noise contribution. Fit quality should be high.

- check_questions:
  - "Is T2_echo consistent with the 2*T1 limit?"
  - "Is the decay well-fitted by a single exponential or Gaussian?"
  - "Is T2_echo stable compared to recent measurements?"

## Input parameters

- qubit_frequency: Loaded from DB
- hpi_amplitude: Loaded from DB
- hpi_length: Loaded from DB
- readout_amplitude: Loaded from DB
- readout_frequency: Loaded from DB
- readout_length: Readout pulse length (ns)

## Output parameters

- t2_echo: T2 echo time (μs)

## Run parameters

- time_range: Time range for T2 echo time (ns)
- shots: Number of shots for T2 echo time
- interval: Time interval for T2 echo time (ns)

## Common failure patterns

- [critical] T2_echo << 2*T1
  - cause: residual high-frequency noise not refocused by single echo
  - visual: decay much faster than expected from T1 measurement
  - next: try CPMG (multiple echoes) to identify noise spectrum
- [warning] Non-exponential decay
  - cause: 1/f noise spectrum or multiple noise sources
  - visual: decay does not fit single exponential, stretched or compressed shape
  - next: try stretched exponential fit, investigate noise spectrum
- [warning] T2_echo > 2*T1
  - cause: measurement artifact; fitting or readout calibration issue
  - visual: decay appears slower than physically expected
  - next: verify T1 measurement, check readout calibration

## Tips for improvement

- Compare T2_echo with T2* (Ramsey) to quantify low-frequency noise contribution.
- If T2_echo is much shorter than 2*T1, try CPMG (multiple echoes) to identify noise spectrum.
- Ensure π pulse is well-calibrated; a bad refocusing pulse degrades echo amplitude.

## Analysis guide

1. Check the decay fit quality (R²) and identify the decay model (exponential vs Gaussian).
2. Compare T2_echo with 2*T1 to assess the noise regime.
3. Compare T2_echo with T2* to quantify the low-frequency noise contribution.
4. Review recent history for trends or instability.
5. If T2_echo << 2*T1, investigate high-frequency noise sources.

## Prerequisites

- CheckT1
- CheckQubitFrequency

## Related context

- history(last_n=5)
- neighbor_qubits(frequency, t1, t2_echo)
