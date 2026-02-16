# ReadoutClassification

Calibrates and evaluates readout state discrimination (|0⟩ vs |1⟩ classification).

## What it measures

Readout assignment fidelity – probability of correctly identifying qubit state.

## Physical principle

Prepare |0⟩ and |1⟩ states, measure IQ data, train classifier, evaluate confusion matrix.

## Expected result

Two IQ blob clusters; clear separation indicates good discrimination.

- result_type: scatter_plot
- x_axis: I quadrature (a.u.)
- y_axis: Q quadrature (a.u.)
- good_visual: two well-separated IQ clusters with minimal overlap, clear classification boundary

![Readout classification](figures/ReadoutClassification/0.png)

## Evaluation criteria

Average readout fidelity should be high with low asymmetry between |0⟩ and |1⟩ assignment errors.

- check_questions:
  - "Are the IQ blobs well-separated with minimal overlap?"
  - "Is the assignment fidelity symmetric for |0⟩ and |1⟩?"
  - "Is the average readout fidelity meeting the target?"

## Output parameters

- average_readout_fidelity: Mean of P(0|0) and P(1|1); expected > 0.95
- p00: P(assign 0 | prepared 0); expected > 0.95
- p11: P(assign 1 | prepared 1); expected > 0.95

## Common failure patterns

- [critical] Overlapping IQ blobs
  - cause: insufficient dispersive shift or readout power
  - visual: IQ clusters overlap significantly, poor separation
  - next: check dispersive shift, optimize readout amplitude
- [warning] T1 decay during readout
  - cause: |1⟩ relaxes to |0⟩ before measurement completes
  - visual: asymmetric errors: P(0|1) >> P(1|0)
  - next: shorten readout pulse, check T1
- [warning] Readout-induced transitions
  - cause: measurement drives qubit transitions
  - visual: increased error rate at high readout power
  - next: reduce readout amplitude, check for non-QND effects
- [info] Classifier bias
  - cause: asymmetric errors for |0⟩ vs |1⟩
  - visual: confusion matrix has large off-diagonal asymmetry
  - next: retrain classifier, check IQ blob balance

## Tips for improvement

- If |1⟩→|0⟩ error >> |0⟩→|1⟩ error, suspect T1 during readout.
- Optimize readout amplitude and duration jointly.
- Consider neural network classifier for better discrimination.

## Analysis guide

1. Examine IQ scatter plot for blob separation and overlap.
2. Check the confusion matrix for error symmetry.
3. If P(0|1) >> P(1|0), T1 during readout is the limiting factor.
4. Compare fidelity with dispersive shift expectations.
5. Verify readout amplitude is at the optimal point.

## Prerequisites

- CheckOptimalReadoutAmplitude
- CheckDispersiveShift

## Related context

- history(last_n=5)
