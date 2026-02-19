# CheckStatus

Checks the status of the experiment and control hardware.

## What it measures

Overall experiment status – verifies that the control system and hardware are in a healthy, operational state.

## Physical principle

Diagnostic query to the experiment controller. No physical measurement is performed; the task polls the system for readiness and error conditions.

## Expected result

A status report confirming all subsystems are operational.

- result_type: status_report
- good_visual: all subsystems report healthy status with no errors

## Evaluation criteria

All subsystems should report a healthy state. Any error or warning indicates a hardware or configuration issue that must be resolved before proceeding with calibration.

- check_questions:
  - "Do all subsystems report a healthy status?"
  - "Are there any error or warning messages?"

## Input parameters

None.

## Output parameters

None.

## Run parameters

None.

## Common failure patterns

- [critical] Subsystem not responding
  - cause: hardware disconnected or powered off
  - next: check physical connections and power supply
- [critical] Error status reported
  - cause: hardware fault or misconfiguration
  - next: review error details and consult hardware documentation

## Tips for improvement

- Run this task first before any calibration to catch hardware issues early.
- If status check fails, resolve all issues before proceeding.

## Analysis guide

1. Review the status output for any errors or warnings.
2. If errors exist, address them before running further tasks.
3. Confirm all control and readout lines are operational.

## Prerequisites

None (this is typically the first task in a calibration workflow).

## Related context

- history(last_n=5)
