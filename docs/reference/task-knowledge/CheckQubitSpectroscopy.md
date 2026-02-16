# CheckQubitSpectroscopy

High-resolution qubit spectroscopy to measure qubit transition frequencies and anharmonicity.

## What it measures

Qubit transition frequencies – measures the ground-to-excited state frequency (f_01) and optionally the excited-to-second-excited state frequency (f_12) to determine the qubit anharmonicity (alpha = f_12 - f_01).

## Physical principle

Qubit spectroscopy with peak detection and analysis: a probe tone is swept across the frequency range near the qubit's expected transition while monitoring the readout resonator. The f_01 peak appears as the dominant absorption feature. The f_12 transition, typically at a lower frequency (negative anharmonicity for transmons), appears as a secondary, weaker feature.

## Expected result

Spectroscopy trace with clear f_01 peak and optionally f_12 peak, with annotated frequency markers.

- result_type: spectroscopy
- x_axis: Frequency (GHz)
- y_axis: Readout signal (dB)
- good_visual: sharp f_01 peak clearly above noise, with f_12 peak visible at expected offset

## Evaluation criteria

The f_01 peak should be well-resolved with sufficient height. If f_12 is detected, the anharmonicity should be in the expected range for the qubit type (typically -200 to -300 MHz for transmons).

- check_questions:
  - "Is the f_01 peak clearly detected above the height threshold?"
  - "Is the f_12 peak detected at a reasonable distance from f_01?"
  - "Is the anharmonicity in the expected range for this qubit type?"
  - "Is the peak width consistent with expected coherence times?"

## Output parameters

- qubit_frequency: Estimated qubit frequency f_01 (GHz)
- anharmonicity: Anharmonicity alpha = f_12 - f_01 (GHz); typically negative for transmons

## Common failure patterns

- [critical] No f_01 peak detected
  - cause: qubit frequency outside scan range, insufficient drive power, or qubit not operational
  - visual: flat trace with no peaks above threshold
  - next: widen scan range, increase drive power, run CheckQubitFrequencies first
- [warning] f_12 not detected
  - cause: f_12 too weak, outside search distance, or threshold too high
  - visual: only f_01 peak visible
  - next: adjust f12_distance_min/max and f12_height_min parameters
- [warning] Spurious peaks
  - cause: TLS defects, drive harmonics, or crosstalk
  - visual: additional unexpected peaks in the spectroscopy trace
  - next: verify peaks by varying drive power; real qubit peaks shift with power differently than TLS

## Tips for improvement

- Run CheckQubitFrequencies first to narrow the scan range.
- Adjust binarize_threshold_sigma parameters if peak detection is unreliable.
- For transmons, expect anharmonicity around -200 to -300 MHz.
- If f_12 is not detected, try relaxing the height threshold (f12_height_min).

## Analysis guide

1. Verify f_01 peak is clearly detected and at reasonable frequency.
2. Check if f_12 is detected and compute anharmonicity.
3. Verify anharmonicity is in expected range for qubit type.
4. Review quality level; if <= 2, investigate peak quality issues.
5. Compare with previous measurements for drift detection.

## Prerequisites

- CheckResonatorSpectroscopy (provides readout_frequency)

## Related context

- history(last_n=5)
