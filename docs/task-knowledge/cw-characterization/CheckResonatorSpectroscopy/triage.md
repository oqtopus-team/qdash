# CheckResonatorSpectroscopy AI Triage Guide

This guide helps the AI decide whether a resonator-spectroscopy result is operationally usable for automatic follow-up.

## Decision focus

- Judge the full MUX map first, then the assigned qubit frequency.
- Prefer `PASS` only when all expected resonators are visible and the assigned `readout_frequency` is clearly supported by the annotated peak.
- Prefer `REVIEW` when the map is partially usable but ambiguity remains around peak count, MUX ordering, or peak assignment.
- Prefer `FAIL` when the scan does not support reliable readout-frequency assignment.

## MUX-specific rules

- This is a MUX-level task. The representative result can affect multiple qubits, so weak evidence should not be auto-approved.
- A peak count below the expected `num_resonators` is usually a `FAIL` unless the task parameters intentionally reduced the expected count.
- If peaks are present but one assignment is ambiguous because of overlap or crossing trajectories, prefer `REVIEW` instead of `PASS`.
- Mild frequency drift can still be acceptable when the resonance structure is clean and the assigned qubit peak is unambiguous.

## Typical review triggers

- One or more resonators are missing from the annotated result.
- Two resonators are so close that the assigned qubit frequency may map to the wrong MUX position.
- High-power and low-power traces disagree strongly, suggesting unstable detection or a wrong peak family.
- The assigned `readout_frequency` sits far from the visually strongest resonance for that qubit position.
- The map shows no clear power dependence and the detected points look dominated by noise or artifacts.

## Recommended labels

- Use `NO_SIGNAL` when resonator dips are not clearly observable or most expected peaks are absent.
- Use `BAD_FIT` when peaks exist but the detected/annotated assignment is inconsistent with the visible resonance structure.
- Use `OUTLIER` when the map is readable but the resulting frequency placement is suspicious compared with the rest of the MUX.
- Use `PASS` only when the figure supports the assigned frequency without material ambiguity.
