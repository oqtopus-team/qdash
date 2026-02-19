# CheckDRAGPIPulse

Validates DRAG-corrected π pulse quality to suppress leakage to |2⟩.

## What it measures

Gate fidelity of DRAG-corrected X180 pulse.

## Physical principle

DRAG adds a derivative quadrature component to suppress leakage during fast gates. Validate by repeated pulse application.

## Expected result

Population oscillation with high contrast under repeated DRAG π pulses.

- result_type: oscillation
- x_axis: Number of DRAG π pulse repetitions
- y_axis: P(|1⟩)
- good_visual: sharp 0/1 alternation with very slow contrast decay, better than non-DRAG version

![DRAG PI pulse error amplification](./0.png)

## Evaluation criteria

Gate fidelity should exceed the non-DRAG version; leakage to |2⟩ should be minimal.

- check_questions:
  - "Is the gate fidelity >99.5%?"
  - "Is the leakage to |2⟩ <0.1%?"
  - "Is the DRAG version better than the non-DRAG CheckPIPulse?"

## Input parameters

- qubit_frequency: Loaded from DB
- drag_pi_amplitude: Loaded from DB
- drag_pi_length: Loaded from DB
- drag_pi_beta: Loaded from DB
- readout_amplitude: Loaded from DB
- readout_frequency: Loaded from DB
- readout_length: Readout pulse length (ns)

## Output parameters

None.

## Run parameters

- repetitions: Number of repetitions for the PI pulse (a.u.)
- interval: Time interval (ns)

## Common failure patterns

- [critical] DRAG coefficient mis-tuned
  - cause: beta parameter not at optimal value for leakage suppression
  - visual: residual leakage visible as population decay faster than decoherence
  - next: rescan DRAG beta parameter
- [warning] Amplitude drift
  - cause: accumulated rotation error from amplitude miscalibration
  - visual: population drift from ideal 0/1 alternation
  - next: recalibrate amplitude with CreateDRAGPIPulse
- [info] Anharmonicity too small
  - cause: DRAG correction insufficient for fast gates when anharmonicity is marginal
  - visual: leakage persists despite DRAG optimization
  - next: slow down gate, consider alternative pulse shapes

## Tips for improvement

- Compare error rate with non-DRAG π pulse to quantify improvement.
- If leakage persists, try scanning DRAG beta parameter.
- Ensure anharmonicity is well-characterized before DRAG tuning.

## Analysis guide

1. Compare gate fidelity with the non-DRAG CheckPIPulse result.
2. Check for leakage signatures in the decay pattern.
3. Verify DRAG beta is at the optimal value.
4. If improvement is marginal, consider whether DRAG is necessary for this qubit.

## Prerequisites

- CreateDRAGPIPulse
- CheckPIPulse

## Related context

- history(last_n=5)
