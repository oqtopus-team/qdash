# Task Knowledge

Calibration task knowledge base for QDash copilot analysis. Each page describes what a task measures, its physical principle, expected results, evaluation criteria, common failure patterns, and tips for improvement.

## Box Setup

| Task | Description |
|------|-------------|
| [CheckStatus](./CheckStatus) | Checks the status of the experiment and control hardware. |
| [LinkUp](./LinkUp) | Initializes and links up the control box hardware. |
| [DumpBox](./DumpBox) | Dumps diagnostic information from all control boxes. |
| [CheckNoise](./CheckNoise) | Checks the noise levels in the control and readout system. |
| [Configure](./Configure) | Loads and applies the full calibration state configuration to the control boxes. |
| [ReadoutConfigure](./ReadoutConfigure) | Configures readout parameters for a specified subset of qubits. |

## System

| Task | Description |
|------|-------------|
| [CheckSkew](./CheckSkew) | Measures and corrects time skew between multiple control boxes. |

## CW Spectroscopy

| Task | Description |
|------|-------------|
| [CheckResonatorFrequencies](./CheckResonatorFrequencies) | Coarse frequency scan to locate readout resonator resonance frequencies. |
| [CheckResonatorSpectroscopy](./CheckResonatorSpectroscopy) | High-resolution 2D spectroscopy of all resonators in a readout multiplexer (MUX). |
| [CheckReflectionCoefficient](./CheckReflectionCoefficient) | Measures the resonator reflection coefficient to extract resonator frequency and coupling rates. |
| [CheckElectricalDelay](./CheckElectricalDelay) | Measures the electrical delay in the readout line. |
| [CheckReadoutAmplitude](./CheckReadoutAmplitude) | Optimizes readout pulse amplitude by sweeping amplitude and measuring signal-to-noise ratio. |
| [CheckQubitFrequencies](./CheckQubitFrequencies) | Coarse qubit frequency scan to locate the qubit transition frequency. |
| [CheckQubitSpectroscopy](./CheckQubitSpectroscopy) | High-resolution qubit spectroscopy to measure qubit transition frequencies and anharmonicity. |

## One-Qubit Calibration

| Task | Description |
|------|-------------|
| [CheckQubit](./CheckQubit) | Quick qubit validation via brief Rabi oscillation check. |
| [CheckQubitFrequency](./CheckQubitFrequency) | Measures qubit transition frequency via Ramsey-based detuning calibration. |
| [CheckReadoutFrequency](./CheckReadoutFrequency) | Calibrates the readout resonator frequency for optimal state discrimination. |
| [CheckRabi](./CheckRabi) | Measures Rabi oscillation to extract drive amplitude, frequency, and contrast. |
| [CheckT1](./CheckT1) | Measures T1 energy-relaxation time via exponential decay of the excited state. |
| [CheckT2Echo](./CheckT2Echo) | Measures T2 echo (Hahn echo) coherence time, refocusing low-frequency noise. |
| [CheckRamsey](./CheckRamsey) | Measures T2* (free-induction) dephasing time and fine-tunes qubit frequency via Ramsey fringes. |
| [CheckDispersiveShift](./CheckDispersiveShift) | Measures dispersive shift (χ) between qubit and readout resonator. |
| [CheckOptimalReadoutAmplitude](./CheckOptimalReadoutAmplitude) | Optimizes readout pulse amplitude for best state discrimination. |
| [ReadoutClassification](./ReadoutClassification) | Calibrates and evaluates readout state discrimination (|0⟩ vs |1⟩ classification). |

## Gate Calibration

| Task | Description |
|------|-------------|
| [CheckPIPulse](./CheckPIPulse) | Validates π pulse quality by repeated application and population measurement. |
| [CheckHPIPulse](./CheckHPIPulse) | Validates π/2 pulse quality by repeated application and population measurement. |
| [CheckDRAGPIPulse](./CheckDRAGPIPulse) | Validates DRAG-corrected π pulse quality to suppress leakage to |2⟩. |
| [CheckDRAGHPIPulse](./CheckDRAGHPIPulse) | Validates DRAG-corrected π/2 pulse quality for leakage suppression. |
| [CreatePIPulse](./CreatePIPulse) | Calibrates π (X180) gate pulse amplitude via Rabi-based fitting. |
| [CreateHPIPulse](./CreateHPIPulse) | Calibrates π/2 (X90) gate pulse amplitude via Rabi-based fitting. |
| [CreateDRAGPIPulse](./CreateDRAGPIPulse) | Calibrates DRAG beta and amplitude for leakage-suppressed π pulse. |
| [CreateDRAGHPIPulse](./CreateDRAGHPIPulse) | Calibrates DRAG beta and amplitude for leakage-suppressed π/2 pulse. |

## Two-Qubit Calibration

| Task | Description |
|------|-------------|
| [CheckCrossResonance](./CheckCrossResonance) | Measures cross-resonance (CR) interaction strength between coupled qubits. |
| [ChevronPattern](./ChevronPattern) | Measures qubit response vs frequency and time to map the chevron pattern. |
| [CheckZX90](./CheckZX90) | Validates ZX90 two-qubit gate fidelity via process or state fidelity measurement. |
| [CreateZX90](./CreateZX90) | Calibrates ZX90 (CNOT-equivalent) two-qubit gate from cross-resonance interaction. |
| [CheckBellState](./CheckBellState) | Prepares Bell state (|00⟩+|11⟩)/√2 and measures state fidelity. |
| [CheckBellStateTomography](./CheckBellStateTomography) | Full density matrix tomography of the Bell state for detailed characterization. |

## Benchmarking

| Task | Description |
|------|-------------|
| [RandomizedBenchmarking](./RandomizedBenchmarking) | Measures average gate error rate via randomized benchmarking (RB). |
| [X90InterleavedRandomizedBenchmarking](./X90InterleavedRandomizedBenchmarking) | Measures X90 (π/2) gate-specific error rate via interleaved randomized benchmarking. |
| [X180InterleavedRandomizedBenchmarking](./X180InterleavedRandomizedBenchmarking) | Measures X180 (π) gate-specific error rate via interleaved randomized benchmarking. |
| [ZX90InterleavedRandomizedBenchmarking](./ZX90InterleavedRandomizedBenchmarking) | Measures ZX90 two-qubit gate error rate via interleaved randomized benchmarking. |
