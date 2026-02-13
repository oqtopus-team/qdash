# CheckDRAGPIPulse

Validates DRAG-corrected π pulse quality to suppress leakage to |2⟩.

## What it measures

Gate fidelity of DRAG-corrected X180 pulse.

## Physical principle

DRAG adds a derivative quadrature component to suppress leakage during fast gates. Validate by repeated pulse application.

## Expected curve

Population oscillation with high contrast under repeated DRAG π pulses.

## Evaluation criteria

Gate fidelity >99.5%; leakage to |2⟩ <0.1%.

## Common failure patterns

- DRAG coefficient mis-tuned – residual leakage visible as population decay.
- Amplitude drift – accumulated rotation error.
- Anharmonicity too small – DRAG correction insufficient for fast gates.

## Tips for improvement

- Compare error rate with non-DRAG π pulse to quantify improvement.
- If leakage persists, try scanning DRAG beta parameter.
- Ensure anharmonicity is well-characterized before DRAG tuning.
