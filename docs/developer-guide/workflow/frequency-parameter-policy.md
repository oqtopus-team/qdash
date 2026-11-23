# Frequency Parameter Policy

Keep measured device frequencies separate from operational drive frequencies.

## Parameter roles

| Parameter | Meaning |
| --- | --- |
| `coarse_qubit_frequency` | Exploration estimate |
| `qubit_frequency` | Measured qubit frequency |
| `control_frequency` | Operating control drive |
| `resonator_frequency` | Measured resonator frequency |
| `readout_frequency` | Operating readout drive |

History records measurements; current calibration holds accepted values. A newer measurement
need not be accepted. Later accepted publications replace earlier ones without ranking task names.

## Qubit and control frequency

| Task | Publishes when accepted |
| --- | --- |
| Qubit spectroscopy, control-amplitude check | Coarse qubit and control frequencies |
| Adaptive Chevron, Chevron, Ramsey | Qubit and control frequencies |

Ordinary tasks prefer `control_frequency`, falling back to `qubit_frequency` only when absent.
Bring-up's control-amplitude and Adaptive Chevron tasks instead allow the coarse fallback.
Exploration never overwrites the measured qubit frequency, but can replace its operating drive.
A later task failure does not roll back earlier accepted publications.

## Resonator and readout frequency

| Task | Publishes when accepted |
| --- | --- |
| Resonator spectroscopy | Measured resonance and the same value as readout drive |
| CKP | Fitted resonance and optimized readout drive |
| Coarse readout optimization | Readout drive, without replacing resonance |

Ordinary tasks prefer `readout_frequency`, falling back to `resonator_frequency` when absent.
Repeating spectroscopy resets the drive to resonance; optimize readout again when needed.

## EF and FH frequency and configuration

EF and FH keep measured and operating frequencies separate too. Run `ConfigureEF` in the same
worker session before dependent tasks. The default layout is `ge-ef-cr`; FH requires `ge-ef-fh`.
Run ordinary `Configure` to restore `ge-cr-cr` before CR work.

Adaptive EF Chevron publishes `ef_frequency`, `control_frequency_ef`, and anharmonicity.
Adaptive FH Chevron publishes `fh_frequency` and `control_frequency_fh` and requires calibrated
GE HPI and EF pi pulses. Missing search frequencies use Qubex-derived seeds, not persisted
anharmonicity. Qubex's `x180()` can prefer existing note pulses over restored HPI/PI inputs;
a new execution does not clear those notes.

## Runtime frequency resolution

Declare operational inputs with explicit `fallback_parameter_names`; reserve aliases for names
with the same meaning. Record the actual source and any override. An operational override is
not a physical measurement. Snapshot re-execution uses recorded effective inputs; see
[Parameter Resolution](./parameter-resolution.md).

## Coarse readout scan settings

`CheckCoarseReadoutParams` records control/readout frequencies and amplitudes, scopes overrides
to the scan, and restores them afterward. Run parameters define the sweep and shared readout
duration. Reference amplitude must be finite and in `(0, 1]`; generated amplitudes are capped
and deduplicated.

### Coarse readout R² validation

Accept outputs only when the selected scan point has finite R² strictly above 0.6 and at most 1.
Do not average points, substitute another point, or skip a missing selection. Rejection retains
diagnostics but publishes neither frequency nor amplitude. CKP has its own finite R² gate,
strictly above 0.7, and rejects invalid required fit values.

## Manual correction

Spectroscopy corrections change operational values only: resonator results allow readout
frequency/amplitude; qubit results allow control frequency/coarse control amplitude.
Measured frequencies remain experiment-owned, including when correcting from a failed result.

## YAML export

Accepted measured and operational frequencies export to separate named YAML files.
Seed import accepts operational frequency/amplitude files, never measured qubit or resonator
frequency files. Publication must be enabled and validation must pass; see
[Calibration Data Lifecycle](./calibration-data-lifecycle.md).

## Implementation and tests

Declarations and publication targets live in `src/qdash/workflow/calibtasks/qubex/`.
When changing them, test input fallback, destination selection, snapshot behavior, and rejected
outputs with `task test-workflow`. The user procedure is [Task Parameters](../../user-guide/task-parameters.md).
