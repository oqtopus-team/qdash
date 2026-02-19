# Configure

Loads and applies the full calibration state configuration to the control boxes.

## What it measures

No measurement is performed. This task loads the saved calibration state (frequencies, amplitudes, timing parameters) from configuration files and pushes them to all control boxes.

## Physical principle

No physical measurement. This is a state management task that restores a previously saved calibration configuration to the hardware, ensuring all control parameters are set to known values.

## Expected result

Full calibration state loaded and pushed to all control boxes successfully.

- result_type: configuration
- good_visual: state loaded and pushed without errors

## Evaluation criteria

State should load and push without errors. All boxes should acknowledge the configuration update.

- check_questions:
  - "Did the state load from configuration files without errors?"
  - "Was the configuration successfully pushed to all boxes?"

## Input parameters

None.

## Output parameters

None.

## Run parameters

None.

## Common failure patterns

- [critical] Configuration file not found
  - cause: missing or misnamed configuration files
  - next: verify config_path and params_path are correct and files exist
- [critical] Push failure
  - cause: hardware communication error or incompatible configuration
  - next: check LinkUp status and configuration file compatibility
- [warning] Stale configuration
  - cause: configuration files are outdated relative to hardware changes
  - next: re-run calibration to generate updated configuration

## Tips for improvement

- Always run Configure after LinkUp to ensure hardware has the correct calibration state.
- Keep configuration files version-controlled for reproducibility.
- Compare loaded state with expected values after pushing.

## Analysis guide

1. Verify configuration files exist and are up to date.
2. Confirm state was loaded and pushed successfully.
3. Consider running CheckStatus after Configure to verify system health.

## Prerequisites

- LinkUp

## Related context

- history(last_n=5)
