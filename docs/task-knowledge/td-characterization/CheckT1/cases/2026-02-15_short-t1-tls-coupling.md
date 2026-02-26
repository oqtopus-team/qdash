# Short T1 due to TLS coupling

- date: 2026-02-15
- severity: critical
- chip_id: CHIP-01
- qid: Q12
- status: resolved

## Symptom

T1 measured at 15 us, which is abnormally short compared to the typical 30-50 us range for this chip.

## Root cause

TLS defect located near the qubit frequency, accelerating energy relaxation.

## Resolution

Shifted qubit frequency by 50 MHz to avoid the TLS defect. T1 recovered to 45 us.

## Lesson learned

- When T1 degrades suddenly, suspect TLS coupling first.
- Frequency shift can often circumvent TLS defects.
- Monitor T1 stability over time to distinguish TLS from other loss mechanisms.
