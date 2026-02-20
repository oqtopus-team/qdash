# LinkUp

Initializes and links up the control box hardware.

## What it measures

Hardware link status – establishes communication between the host system and the control boxes (FPGA-based quantum control hardware).

## Physical principle

No physical measurement. This task performs hardware initialization: establishing network/bus connections to the control boxes and verifying bidirectional communication.

## Expected result

Successful link-up of all control boxes with confirmed communication.

- result_type: status_report
- good_visual: all boxes linked and communicating without errors

## Evaluation criteria

All control boxes should link up successfully. Timeouts or communication errors indicate hardware or network issues.

- check_questions:
  - "Did all control boxes link up successfully?"
  - "Were there any timeout or communication errors?"

## Input parameters

None.

## Output parameters

None.

## Run parameters

None.

## Common failure patterns

- [critical] Link-up timeout
  - cause: control box powered off, network issue, or firmware mismatch
  - next: check power, network cables, and firmware versions
- [critical] Partial link-up
  - cause: one or more boxes not responding
  - next: identify which box failed and check its individual status

## Tips for improvement

- Ensure all control boxes are powered on and connected before running.
- Check that firmware versions are compatible with the host software.
- If link-up fails intermittently, check network stability.

## Analysis guide

1. Confirm all expected control boxes are linked.
2. If any box fails to link, check physical connections first.
3. Verify firmware compatibility if connections are physically sound.

## Related context

- history(last_n=5)
