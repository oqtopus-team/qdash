# ReadoutConfigure

Configures readout parameters for a specified subset of qubits.

## What it measures

No measurement is performed. This task applies readout configuration (frequencies, amplitudes) to the control hardware for a selected set of qubits.

## Physical principle

No physical measurement. This is a configuration task that sets readout resonator frequencies for specified qubits and disables (sets to NaN) frequencies for qubits not in the target list.

## Expected result

Readout parameters successfully applied to the hardware for the specified qubits.

- result_type: configuration
- good_visual: configuration applied without errors

## Evaluation criteria

Configuration should apply without errors. The specified qubits should have valid readout parameters, while excluded qubits should be disabled.

- check_questions:
  - "Did the configuration apply without errors?"
  - "Are the correct qubits enabled for readout?"

## Input parameters

None.

## Output parameters

None.

## Run parameters

- qubits: List of muxes to check skew (a.u.)

## Common failure patterns

- [critical] Configuration push failure
  - cause: hardware communication error or invalid parameter values
  - next: check hardware link status and parameter validity
- [warning] Empty qubit list
  - cause: no qubits specified in run parameters
  - next: verify the qubit list in run parameters is correctly set

## Tips for improvement

- Use this task to selectively configure readout for a subset of qubits when full-chip calibration is not needed.
- Verify qubit IDs match the expected chip layout before running.

## Analysis guide

1. Confirm the target qubit list matches expectations.
2. Verify configuration was pushed to hardware without errors.
3. Check that excluded qubits are properly disabled.

## Prerequisites

- LinkUp
- Configure

## Related context

- history(last_n=5)
