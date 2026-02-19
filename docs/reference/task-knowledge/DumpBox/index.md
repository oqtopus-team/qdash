# DumpBox

Dumps diagnostic information from all control boxes.

## What it measures

Control box internal state – extracts configuration, firmware version, register values, and other diagnostic data from each control box.

## Physical principle

No physical measurement. This task reads internal registers and configuration from the FPGA-based control hardware for diagnostic and debugging purposes.

## Expected result

A dictionary of diagnostic information keyed by box ID, containing hardware configuration and status details.

- result_type: diagnostic_dump
- good_visual: complete diagnostic data for all boxes without errors

## Evaluation criteria

All boxes should return complete diagnostic information. Missing or incomplete data indicates communication issues.

- check_questions:
  - "Is diagnostic data available for all expected boxes?"
  - "Are there any unexpected register values or error flags?"

## Output parameters

None.

## Common failure patterns

- [warning] Incomplete dump
  - cause: communication interrupted during data retrieval
  - next: retry the dump; check network stability
- [critical] Box not found
  - cause: box not linked or powered off
  - next: run LinkUp first, check hardware connections

## Tips for improvement

- Use this task for debugging hardware issues.
- Compare dumps before and after configuration changes to verify settings applied correctly.
- Save dumps as reference baselines for troubleshooting.

## Analysis guide

1. Review dump output for each box.
2. Compare with expected configuration values.
3. Flag any unexpected register values or error conditions.

## Prerequisites

- LinkUp

## Related context

- history(last_n=5)
