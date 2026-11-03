---
name: qdash-two-qubit-calibration-diagnosis
description: Diagnose QDash two-qubit calibration quality from CR, ZX90, Bell-state, tomography, coherence-limit, and IRB task results. Use when a coupling calibration completes but gate fidelity, Bell fidelity, or validation quality may be poor.
license: Apache-2.0
compatibility: pi-coding-agent >=0.74, pi-qdash extension
metadata:
  domain: quantum-calibration
  safety_level: read-only-first-write-gated
  preferred_validation_chain: CheckCrossResonance -> CreateZX90 -> CheckZX90 -> CheckBellState -> CheckBellStateTomography -> ZX90InterleavedRandomizedBenchmarking
---

# QDash Two-Qubit Calibration Diagnosis

Use this skill when investigating coupling-level calibration quality, especially when tasks are `completed` but quality may be poor.

## Principles

- Treat `completed` as execution status, not proof of calibration quality.
- Diagnose from evidence before suggesting operational actions.
- Resolve cooldown membership before comparing calibrations or coherence limits. Keep different cooldowns separate, and distinguish a cooldown boundary from an in-cooldown wiring change.
- Prefer read-only tools first: `qdash_list_cooldowns`, `qdash_target_report`, `qdash_list_task_results`, `qdash_get_task_result`, `qdash_analyze_figure_json`, and `qdash_get_task_figures`.
- Do not rerun RB first when validation quality is suspicious. Walk back through prerequisites.
- Do not commit or apply candidates without explicit user confirmation, and only after downstream validation.

## Standard read-only investigation

For a coupling `cA-B`:

1. Build context with `qdash_list_cooldowns`, `qdash_target_report`, and recent task results for the coupling. Record the cooldown ID for each result and inspect wiring events when measurement conditions may have changed.
2. Inspect the latest same-cooldown tasks in this chain by default, and call `qdash_get_task_knowledge` for each task before interpreting its outputs or figures:
   - `CheckCrossResonance`
   - `CreateZX90`
   - `CheckZX90`
   - `CheckBellState`
   - `CheckBellStateTomography`
   - `Check2QGateCoherenceLimit`
   - `ZX90InterleavedRandomizedBenchmarking`
3. Fetch task details and record:
   - CR: `cr_amplitude`, `cr_phase`, `cancel_amplitude`, `cancel_phase`, `rotary_amplitude`, `zx_rotation_rate`
   - ZX90: `zx90_gate_time`
   - Bell tomography: `bell_state_fidelity`
   - Coherence limit: `two_qubit_gate_coherence_limit`
   - IRB: `zx90_gate_fidelity`, its error, `zx90_depolarizing_rate`, `n_trials`
4. For JSON figures, use `qdash_analyze_figure_json` before manually reading raw Plotly JSON.
5. Summarize symptoms, likely failure mode, and the next *read-only or confirmation-gated* step.

## Interpretation rules

Use `qdash_get_task_knowledge` for `CheckCrossResonance`, `CheckZX90`, `CheckBellState`, `CheckBellStateTomography`, `Check2QGateCoherenceLimit`, and `ZX90InterleavedRandomizedBenchmarking` as applicable. Apply the returned expected-result descriptions, criteria, failure modes, and check questions to the measured outputs.

Treat `completed` only as execution status. Correlate task knowledge with `qdash_analyze_figure_json`, same-cooldown history, and adjacent validation tasks; do not overfit one plot or use IRB alone as a pass signal.

## Recommended action sequence

When validation quality is poor:

```text
Inspect figures/results
-> CheckCrossResonance
-> CreateZX90
-> CheckZX90
-> CheckBellState
-> CheckBellStateTomography
-> ZX90InterleavedRandomizedBenchmarking
```

Each operational step requires explicit confirmation. Validate Bell/tomography before using IRB as the final quality signal.

Historical postmortem cases belong in QDash task knowledge. Retrieve them through `qdash_get_task_knowledge` rather than encoding device-specific values in this procedural skill.
