/**
 * UI-side logical categories for calibration metrics.
 *
 * Categories group metrics under headers in the dropdown menus across the
 * analysis and metrics views. This mapping lives entirely in the UI: the
 * backend metrics config (and the domain YAML it is built from) intentionally
 * has no notion of categories, since grouping is purely a presentation concern.
 *
 * Keyed by the metric `key` exposed by `useMetricsConfig`. Metrics not listed
 * here fall back to an "Other" group (see `metrics-grouping.ts`).
 *
 * The order categories first appear in the metrics list defines their display
 * order; the metrics list follows the backend config order, so keeping these
 * entries aligned with `config/domain/metrics.yaml` preserves a logical layout.
 */
export const METRIC_CATEGORIES: Record<string, string> = {
  // Qubit metrics
  readout_frequency: "Frequency",
  qubit_frequency: "Frequency",
  anharmonicity: "Frequency",
  t1: "Coherence",
  t1_average: "Coherence",
  t2_echo: "Coherence",
  t2_echo_average: "Coherence",
  t2_star: "Coherence",
  average_readout_fidelity: "Readout",
  average_gate_fidelity: "Single-Qubit Gate",
  x90_gate_fidelity: "Single-Qubit Gate",
  x180_gate_fidelity: "Single-Qubit Gate",
  maximum_rabi_frequency: "Control",
  hpi_amplitude: "Control",
  hpi_length: "Control",
  one_qubit_gate_coherence_limit: "Single-Qubit Gate",
  // Coupling metrics
  zx90_gate_fidelity: "Two-Qubit Gate",
  bell_state_fidelity: "Two-Qubit Gate",
  zx90_gate_time: "Two-Qubit Gate",
  two_qubit_gate_coherence_limit: "Two-Qubit Gate",
  static_zz_interaction: "Interaction",
};

/**
 * Resolve the logical category for a metric key.
 *
 * @param key - Metric key (e.g. `"t1"`).
 * @returns The configured category, or `undefined` when the key is unmapped.
 */
export function getMetricCategory(key: string): string | undefined {
  return METRIC_CATEGORIES[key];
}
