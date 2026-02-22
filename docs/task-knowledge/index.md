# Task Knowledge

Calibration task knowledge base for QDash copilot analysis. Each page describes what a task measures, its physical principle, expected results, evaluation criteria, common failure patterns, and tips for improvement.

## Box Setup

| Task | Description |
|------|-------------|
| [CheckStatus](./box-setup/CheckStatus) | Checks the status of the experiment and control hardware. |
| [LinkUp](./box-setup/LinkUp) | Initializes and links up the control box hardware. |
| [DumpBox](./box-setup/DumpBox) | Dumps diagnostic information from all control boxes. |
| [CheckNoise](./box-setup/CheckNoise) | Checks the noise levels in the control and readout system. |
| [Configure](./box-setup/Configure) | Loads and applies the full calibration state configuration to the control boxes. |
| [ReadoutConfigure](./box-setup/ReadoutConfigure) | Configures readout parameters for a specified subset of qubits. |

## System

| Task | Description |
|------|-------------|
| [CheckSkew](./system/CheckSkew) | Measures and corrects time skew between multiple control boxes. |

## CW Characterization

| Task | Description |
|------|-------------|
| [CheckResonatorFrequencies](./cw-characterization/CheckResonatorFrequencies) | Coarse frequency scan to locate readout resonator resonance frequencies. |
| [CheckResonatorSpectroscopy](./cw-characterization/CheckResonatorSpectroscopy) | High-resolution 2D spectroscopy of all resonators in a readout multiplexer (MUX). |
| [CheckReflectionCoefficient](./cw-characterization/CheckReflectionCoefficient) | Measures the resonator reflection coefficient to extract resonator frequency and coupling rates. |
| [CheckElectricalDelay](./cw-characterization/CheckElectricalDelay) | Measures the electrical delay in the readout line. |
| [CheckReadoutAmplitude](./cw-characterization/CheckReadoutAmplitude) | Optimizes readout pulse amplitude by sweeping amplitude and measuring signal-to-noise ratio. |
| [CheckQubitFrequencies](./cw-characterization/CheckQubitFrequencies) | Coarse qubit frequency scan to locate the qubit transition frequency. |
| [CheckQubitSpectroscopy](./cw-characterization/CheckQubitSpectroscopy) | High-resolution qubit spectroscopy to measure qubit transition frequencies and anharmonicity. |

## TD Characterization

| Task | Description |
|------|-------------|
| [CheckQubit](./td-characterization/CheckQubit) | Quick qubit validation via brief Rabi oscillation check. |
| [CheckQubitFrequency](./td-characterization/CheckQubitFrequency) | Measures qubit transition frequency via Ramsey-based detuning calibration. |
| [CheckReadoutFrequency](./td-characterization/CheckReadoutFrequency) | Calibrates the readout resonator frequency for optimal state discrimination. |
| [CheckRabi](./td-characterization/CheckRabi) | Measures Rabi oscillation to extract drive amplitude, frequency, and IQ-plane parameters. |
| [CheckT1](./td-characterization/CheckT1) | Measures T1 energy-relaxation time via exponential decay of the excited state. |
| [CheckT2Echo](./td-characterization/CheckT2Echo) | Measures T2 echo (Hahn echo) coherence time, refocusing low-frequency noise. |
| [CheckRamsey](./td-characterization/CheckRamsey) | Measures T2\* (free-induction) dephasing time and fine-tunes qubit frequency via Ramsey fringes. |
| [CheckDispersiveShift](./td-characterization/CheckDispersiveShift) | Measures dispersive shift (χ) between qubit and readout resonator. |
| [CheckOptimalReadoutAmplitude](./td-characterization/CheckOptimalReadoutAmplitude) | Optimizes readout pulse amplitude for best state discrimination. |
| [ReadoutClassification](./td-characterization/ReadoutClassification) | Calibrates and evaluates readout state discrimination (|0⟩ vs |1⟩ classification). |
| [ChevronPattern](./td-characterization/ChevronPattern) | Measures qubit response vs frequency and time to map the chevron pattern. |

## One-Qubit Gate Calibration

| Task | Description |
|------|-------------|
| [CheckPIPulse](./one-qubit-gate-calibration/CheckPIPulse) | Validates π pulse quality by repeated application and population measurement. |
| [CheckHPIPulse](./one-qubit-gate-calibration/CheckHPIPulse) | Validates π/2 pulse quality by repeated application and population measurement. |
| [CheckDRAGPIPulse](./one-qubit-gate-calibration/CheckDRAGPIPulse) | Validates DRAG-corrected π pulse quality to suppress leakage to |2⟩. |
| [CheckDRAGHPIPulse](./one-qubit-gate-calibration/CheckDRAGHPIPulse) | Validates DRAG-corrected π/2 pulse quality for leakage suppression. |
| [CreatePIPulse](./one-qubit-gate-calibration/CreatePIPulse) | Calibrates π (X180) gate pulse amplitude via Rabi-based fitting. |
| [CreateHPIPulse](./one-qubit-gate-calibration/CreateHPIPulse) | Calibrates π/2 (X90) gate pulse amplitude via Rabi-based fitting. |
| [CreateDRAGPIPulse](./one-qubit-gate-calibration/CreateDRAGPIPulse) | Calibrates DRAG beta and amplitude for leakage-suppressed π pulse. |
| [CreateDRAGHPIPulse](./one-qubit-gate-calibration/CreateDRAGHPIPulse) | Calibrates DRAG beta and amplitude for leakage-suppressed π/2 pulse. |

## Two-Qubit Gate Calibration

| Task | Description |
|------|-------------|
| [CheckCrossResonance](./two-qubit-gate-calibration/CheckCrossResonance) | Measures cross-resonance (CR) interaction strength between coupled qubits. |
| [CheckZX90](./two-qubit-gate-calibration/CheckZX90) | Validates ZX90 two-qubit gate fidelity via process or state fidelity measurement. |
| [CreateZX90](./two-qubit-gate-calibration/CreateZX90) | Calibrates ZX90 (CNOT-equivalent) two-qubit gate from cross-resonance interaction. |
| [CheckBellState](./two-qubit-gate-calibration/CheckBellState) | Prepares Bell state (|00⟩+|11⟩)/√2 and measures state fidelity. |
| [CheckBellStateTomography](./two-qubit-gate-calibration/CheckBellStateTomography) | Full density matrix tomography of the Bell state for detailed characterization. |

## Benchmarking

| Task | Description |
|------|-------------|
| [RandomizedBenchmarking](./benchmarking/RandomizedBenchmarking) | Measures average gate error rate via randomized benchmarking (RB). |
| [X90InterleavedRandomizedBenchmarking](./benchmarking/X90InterleavedRandomizedBenchmarking) | Measures X90 (π/2) gate-specific error rate via interleaved randomized benchmarking. |
| [X180InterleavedRandomizedBenchmarking](./benchmarking/X180InterleavedRandomizedBenchmarking) | Measures X180 (π) gate-specific error rate via interleaved randomized benchmarking. |
| [ZX90InterleavedRandomizedBenchmarking](./benchmarking/ZX90InterleavedRandomizedBenchmarking) | Measures ZX90 two-qubit gate error rate via interleaved randomized benchmarking. |

## Calibration Workflows

Standard calibration workflows and their task composition. See [workflow task definitions](https://github.com/oqtopus-team/qdash/blob/develop/src/qdash/workflow/service/tasks.py) for the source of truth.

![Calibration Workflow Pipelines](../diagrams/calibration-workflows.drawio.png)

### Bring-up

MUX-level initial characterization. Identifies resonator and qubit frequencies.

1. [CheckResonatorSpectroscopy](./cw-characterization/CheckResonatorSpectroscopy)
2. [CheckQubitSpectroscopy](./cw-characterization/CheckQubitSpectroscopy)
3. [ChevronPattern](./td-characterization/ChevronPattern)

### 1Q Check

Basic single-qubit characterization.

1. [CheckRabi](./td-characterization/CheckRabi) (#1)
2. [CheckRabi](./td-characterization/CheckRabi) (#2)
3. [CreateHPIPulse](./one-qubit-gate-calibration/CreateHPIPulse)
4. [CheckHPIPulse](./one-qubit-gate-calibration/CheckHPIPulse)
5. CheckT1Average
6. CheckT2EchoAverage
7. [CheckRamsey](./td-characterization/CheckRamsey)

### 1Q Fine-tune

Advanced single-qubit calibration including DRAG pulse optimization, readout classification, and randomized benchmarking.

1. [CheckRabi](./td-characterization/CheckRabi)
2. [CreateHPIPulse](./one-qubit-gate-calibration/CreateHPIPulse)
3. [CheckHPIPulse](./one-qubit-gate-calibration/CheckHPIPulse)
4. [CreatePIPulse](./one-qubit-gate-calibration/CreatePIPulse)
5. [CheckPIPulse](./one-qubit-gate-calibration/CheckPIPulse)
6. [CreateDRAGHPIPulse](./one-qubit-gate-calibration/CreateDRAGHPIPulse)
7. [CheckDRAGHPIPulse](./one-qubit-gate-calibration/CheckDRAGHPIPulse)
8. [CreateDRAGPIPulse](./one-qubit-gate-calibration/CreateDRAGPIPulse)
9. [CheckDRAGPIPulse](./one-qubit-gate-calibration/CheckDRAGPIPulse)
10. [ReadoutClassification](./td-characterization/ReadoutClassification)
11. [RandomizedBenchmarking](./benchmarking/RandomizedBenchmarking)
12. [X90InterleavedRandomizedBenchmarking](./benchmarking/X90InterleavedRandomizedBenchmarking)

### 2Q Calibration

Two-qubit gate calibration from cross-resonance measurement through ZX90 gate creation to Bell state verification.

1. [CheckCrossResonance](./two-qubit-gate-calibration/CheckCrossResonance)
2. [CreateZX90](./two-qubit-gate-calibration/CreateZX90)
3. [CheckZX90](./two-qubit-gate-calibration/CheckZX90)
4. [CheckBellState](./two-qubit-gate-calibration/CheckBellState)
5. [CheckBellStateTomography](./two-qubit-gate-calibration/CheckBellStateTomography)
6. [ZX90InterleavedRandomizedBenchmarking](./benchmarking/ZX90InterleavedRandomizedBenchmarking)

### Full Calibration Pipeline

End-to-end calibration runs in the following order: Bring-up → 1Q Check → Filter → 1Q Fine-tune → Filter → CR Schedule → 2Q Calibration (see diagram above).
