# ChevronPattern

Measures qubit response vs frequency and time to map the chevron pattern.

## What it measures

Chevron pattern – 2D map of qubit excitation vs drive detuning and pulse duration.

## Physical principle

Drive at various frequency detunings and durations; on-resonance gives Rabi oscillations, off-resonance gives faster but smaller oscillations, forming a V-shaped pattern.

## Expected curve

2D color plot with chevron-shaped fringes; vertex at zero detuning (qubit frequency). Fringe spacing increases with detuning.

## Evaluation criteria

Clear fringe visibility; chevron vertex identifiable to <1 MHz precision.

## Common failure patterns

- Low contrast – insufficient drive power or poor readout fidelity.
- Smeared pattern – frequency drift during measurement.
- Asymmetric chevron – higher-order transitions or AC Stark shift.

## Tips for improvement

- Use the chevron vertex to precisely identify qubit frequency before fine calibration.
- The fringe period at zero detuning gives the Rabi frequency.
- If fringes are faint, increase drive amplitude or number of shots.
