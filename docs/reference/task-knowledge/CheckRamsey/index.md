# CheckRamsey

Measures T2* (free-induction) dephasing time and fine-tunes qubit frequency via Ramsey fringes.

## What it measures

T2* dephasing time and residual detuning from the drive frequency.

## Physical principle

X/2 – free evolution τ – X/2 (or Y/2), then measure. Fringes oscillate at the detuning Δf; envelope decays as exp(-τ/T2*).

## Expected result

Damped cosine: oscillation frequency = detuning Δf, decay constant = T2*. If Δf=0, monotonic decay.

- result_type: oscillation
- x_axis: Free evolution time τ (μs)
- y_axis: P(|1⟩)
- fit_model: A * cos(2π·Δf·τ + φ) * exp(-τ/T2*) + B
- typical_range: 10–80 μs for fixed-frequency transmons
- good_visual: clear oscillation fringes with smooth exponential envelope

![X-basis Ramsey fringe](./x_fringe.png)
![Y-basis Ramsey fringe](./y_fringe.png)
![Ramsey interference in XY plane](./xy_spiral.png)

## Evaluation criteria

T2* should satisfy T2* ≤ T2_echo. Fringe frequency should match the intended detuning. Fit quality and fringe visibility should be high.

- check_questions:
  - "Are the Ramsey fringes clearly visible with good contrast?"
  - "Does the fringe frequency match the intended detuning?"
  - "Is T2* consistent with the T2_echo measurement (T2* ≤ T2_echo)?"

## Output parameters

- t2_star: T2* dephasing time; expected 10–80 μs
- detuning: Residual frequency detuning Δf; expected near intended value
- fit_r_squared: Goodness of fit; expected > 0.90

## Common failure patterns

- [critical] T2* << T2_echo
  - cause: dominated by low-frequency noise (1/f flux noise, charge noise)
  - visual: rapid fringe decay, few oscillation periods visible
  - next: investigate low-frequency noise sources, check shielding
- [warning] No visible fringes
  - cause: detuning too small or T2* extremely short
  - visual: flat or monotonically decaying signal
  - next: add artificial detuning (1–5 MHz) for clearer fringes
- [warning] Fringe frequency drift
  - cause: qubit frequency unstable (TLS, thermal)
  - visual: inconsistent fringe spacing, poor fit
  - next: repeat measurement, check for TLS coupling

## Tips for improvement

- Ramsey with artificial detuning (Δf ~ 1–5 MHz) gives clearer fringes for fitting.
- Second-axis (Y/2) Ramsey separates detuning direction (positive vs negative).
- If T2* improves dramatically with echo, the dominant noise is low-frequency and potentially fixable.

## Analysis guide

1. Check fringe visibility and fit quality (R²).
2. Verify the extracted detuning matches the intended value.
3. Compare T2* with T2_echo to quantify low-frequency noise contribution.
4. Review recent history for frequency drift (changing detuning).
5. If T2* is very short, assess whether low-frequency noise mitigation is needed.

## Prerequisites

- CheckQubitFrequency
- CheckT1

## Related context

- history(last_n=5)
- neighbor_qubits(frequency)
