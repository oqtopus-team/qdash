# CheckSkew

Measures and corrects time skew between multiple control boxes.

## What it measures

Inter-box timing skew – measures the relative timing offsets (clock skew) between different control boxes and applies correction to synchronize their clocks.

## Physical principle

Clock synchronization: multiple control boxes share a common reference clock, but signal propagation delays and internal clock distribution cause timing offsets between boxes. This task measures the relative timing by sending synchronized pulses and measuring arrival time differences, then applies skew correction to align all boxes to a common time reference.

## Expected result

Measured skew values for each box pair, with corrections applied to synchronize timing.

- result_type: timing_measurement
- x_axis: Box pairs
- y_axis: Skew (ns)
- good_visual: small, well-defined skew values with successful correction applied

## Evaluation criteria

Skew values should be measurable and correctable. After correction, residual skew should be within the system's timing resolution.

- check_questions:
  - "Are skew values measurable for all box pairs?"
  - "Are the measured skew values within a correctable range?"
  - "Are the skew values consistent with previous measurements?"

## Output parameters

None.

## Common failure patterns

- [critical] Skew measurement fails
  - cause: box not synchronized to reference clock, hardware fault
  - next: verify reference clock distribution, check box connectivity
- [warning] Large skew values
  - cause: cable length mismatch, clock distribution issue
  - visual: skew values larger than typical range
  - next: check clock distribution hardware and cable routing
- [warning] Inconsistent skew across measurements
  - cause: unstable clock or intermittent connection
  - visual: skew values vary significantly between runs
  - next: investigate clock stability, check connectors

## Tips for improvement

- Run after LinkUp and before any multi-qubit calibration tasks.
- The muxes parameter selects which MUXes to synchronize; default covers most standard configurations.
- Skew correction is essential for two-qubit gate calibration accuracy.
- Compare skew values across runs to detect clock drift.

## Analysis guide

1. Review estimated skew values for each box.
2. Verify skew values are within expected range.
3. Check the skew plot for any outliers.
4. Confirm correction was applied successfully.
5. Compare with previous measurements for drift detection.

## Prerequisites

- LinkUp
- Configure

## Related context

- history(last_n=5)
