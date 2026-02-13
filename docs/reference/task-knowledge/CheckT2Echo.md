# CheckT2Echo

Measures T2 echo (Hahn echo) coherence time, refocusing low-frequency noise.

## What it measures

T2 echo – phase coherence time after a Hahn-echo refocusing pulse.

## Physical principle

X/2 – wait τ/2 – π – wait τ/2 – X/2, then measure. Refocuses static and slow noise, revealing intrinsic dephasing.

## Expected curve

Exponential (or Gaussian) decay envelope of echo amplitude vs total delay τ.

## Evaluation criteria

T2_echo > 80 μs acceptable; > 150 μs excellent. Should satisfy T2_echo ≤ 2*T1.

## Common failure patterns

- T2_echo << 2*T1 – residual high-frequency noise not refocused by single echo.
- Non-exponential decay – 1/f noise spectrum or multiple noise sources.
- T2_echo > 2*T1 – measurement artifact; check fitting and readout calibration.

## Tips for improvement

- Compare T2_echo with T2* (Ramsey) to quantify low-frequency noise contribution.
- If T2_echo is much shorter than 2*T1, try CPMG (multiple echoes) to identify noise spectrum.
- Ensure π pulse is well-calibrated; a bad refocusing pulse degrades echo amplitude.

## Related context

- history(last_n=5)
- neighbor_qubits(frequency, t1, t2_echo)
