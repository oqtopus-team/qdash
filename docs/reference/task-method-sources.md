# Task Method Sources

This table lists the published sources used as background reading when the task explanations
(`description`, `when_to_use`, and `prerequisites` in each task's `TaskDocumentation`) were
written, grouped by measurement method. It is documentation only: QDash does not store or
publish these sources with task metadata, and the API and Agent do not return them.

The sources describe the original general method, not the QDash implementation. The task
source and the Qubex functions it calls define what a task actually does, including sweeps,
fits, and stored values, and that implementation can differ from the protocol in a paper; see
[Document a calibration task](../developer-guide/workflow/engine-architecture.md#document-a-calibration-task).

Configuration and software utility tasks (`Configure`, `ConfigureEF`, `ConfigureAll`,
`CorrectCaptureDelay`, `CheckWaveform`, and the fake backend's `FakeBringUp`) have no listed
sources. Some measurement tasks have none because the procedure is Qubex-specific:
`CheckCoarseReadoutParams`, the `Check*Pulse` repetition checks, the EF pulse calibrations,
`EFReadoutClassification`, `CheckZX90`, and `CheckBellState`.

| Method | Tasks | Sources |
| --- | --- | --- |
| Dispersive resonator and qubit spectroscopy | `CheckResonatorSpectroscopy`, `CheckQubitSpectroscopy`, `CheckControlAmplitude` | [Blais et al. 2021](https://doi.org/10.1103/RevModPhys.93.025005), [Reed et al. 2010](https://doi.org/10.1103/PhysRevLett.105.173601), [Koch et al. 2007](https://doi.org/10.1103/PhysRevA.76.042319) |
| Rabi driving, chevrons, and flat-top pulse amplitudes | `CheckRabi`, `CheckChevron`, `CheckAdaptiveChevron`, `CreateHPIPulse`, `CreatePIPulse` | [Krantz et al. 2019](https://doi.org/10.1063/1.5089550) |
| T1, Ramsey, and Hahn echo | `CheckT1`, `CheckRamsey`, `CheckT2Echo`, `CheckT1Average`, `CheckT2EchoAverage` | [Krantz et al. 2019](https://doi.org/10.1063/1.5089550); fluctuations: [Klimov et al. 2018](https://doi.org/10.1103/PhysRevLett.121.090502), [Burnett et al. 2019](https://doi.org/10.1038/s41534-019-0168-5) |
| DRAG pulses | `CreateDRAGHPIPulse`, `CreateDRAGPIPulse` | [Motzoi et al. 2009](https://doi.org/10.1103/PhysRevLett.103.110501), [Gambetta et al. 2011](https://doi.org/10.1103/PhysRevA.83.012308), [Lucero et al. 2010](https://doi.org/10.1103/PhysRevA.82.042339) |
| Single-shot readout | `ReadoutClassification`, `CheckOptimalReadoutAmplitude`, `CheckOptimalReadoutFrequency` | [Walter et al. 2017](https://doi.org/10.1103/PhysRevApplied.7.054020) |
| Higher transmon levels | `CheckAdaptiveEFChevron`, `CheckAdaptiveFHChevron`, `CheckEFRabi`, `CheckGEFRelaxation` | [Koch et al. 2007](https://doi.org/10.1103/PhysRevA.76.042319), [Peterer et al. 2015](https://doi.org/10.1103/PhysRevLett.114.010501) |
| Thermal excited-state population | `CheckThermalExcitation` | [Geerlings et al. 2013](https://doi.org/10.1103/PhysRevLett.110.120501), [Jin et al. 2015](https://doi.org/10.1103/PhysRevLett.114.240501) |
| Noise spectroscopy | `CheckCPMGNoiseSpectroscopy`, `CheckSpinLockSpectroscopy` | [Bylander et al. 2011](https://doi.org/10.1038/nphys1994), [Yan et al. 2013](https://doi.org/10.1038/ncomms3337) (both on flux qubits) |
| Readout-chain characterization | `CheckCKP`, `CheckQuantumEfficiency`, `CheckReadoutMIST` | [Schuster et al. 2005](https://doi.org/10.1103/PhysRevLett.94.123602), [Sete et al. 2015](https://doi.org/10.1103/PhysRevA.92.012325), [Blais et al. 2021](https://doi.org/10.1103/RevModPhys.93.025005), [Bultink et al. 2018](https://doi.org/10.1063/1.5015954), [Sank et al. 2016](https://doi.org/10.1103/PhysRevLett.117.190503), [Khezri et al. 2023](https://doi.org/10.1103/PhysRevApplied.20.054008) |
| Randomized benchmarking | `RandomizedBenchmarking`, `X90InterleavedRandomizedBenchmarking`, `ZX90InterleavedRandomizedBenchmarking` | [Knill et al. 2008](https://doi.org/10.1103/PhysRevA.77.012307), [Magesan et al. 2011](https://doi.org/10.1103/PhysRevLett.106.180504), [Magesan et al. 2012](https://doi.org/10.1103/PhysRevLett.109.080505), [Córcoles et al. 2013](https://doi.org/10.1103/PhysRevA.87.030301) |
| Coherence-limited gate fidelity | `Check1QGateCoherenceLimit`, `Check2QGateCoherenceLimit` | [Abad et al. 2022](https://doi.org/10.1103/PhysRevLett.129.150504) |
| Cross-resonance gate | `CheckCrossResonance`, `CreateZX90` | [Chow et al. 2011](https://doi.org/10.1103/PhysRevLett.107.080502), [Sheldon et al. 2016](https://doi.org/10.1103/PhysRevA.93.060302), [Sundaresan et al. 2020](https://doi.org/10.1103/PRXQuantum.1.020318), [Córcoles et al. 2013](https://doi.org/10.1103/PhysRevA.87.030301) |
| Two-qubit state tomography | `CheckBellStateTomography` | [James et al. 2001](https://doi.org/10.1103/PhysRevA.64.052312), [Steffen et al. 2006](https://doi.org/10.1126/science.1130886) |
| Static ZZ (JAZZ) | `CheckCouplingStrength` | [Takita et al. 2017](https://doi.org/10.1103/PhysRevLett.119.180501), [Ku et al. 2020](https://doi.org/10.1103/PhysRevLett.125.200504) |
