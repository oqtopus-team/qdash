# ReadoutClassification

Calibrates and evaluates readout state discrimination (|0⟩ vs |1⟩ classification).

## What it measures

Readout assignment fidelity – probability of correctly identifying qubit state.

## Physical principle

Prepare |0⟩ and |1⟩ states, measure IQ data, train classifier, evaluate confusion matrix.

## Expected curve

Two IQ blob clusters; clear separation indicates good discrimination.

## Evaluation criteria

Average readout fidelity >95% acceptable; >99% excellent.

## Common failure patterns

- Overlapping IQ blobs – insufficient dispersive shift or readout power.
- T1 decay during readout – |1⟩ relaxes to |0⟩ before measurement completes.
- Readout-induced transitions – measurement drives qubit transitions.
- Classifier bias – asymmetric errors for |0⟩ vs |1⟩.

## Tips for improvement

- If |1⟩→|0⟩ error >> |0⟩→|1⟩ error, suspect T1 during readout.
- Optimize readout amplitude and duration jointly.
- Consider neural network classifier for better discrimination.
