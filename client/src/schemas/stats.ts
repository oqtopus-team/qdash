/**
 * Generated by orval v7.3.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { StatsAverageValue } from "./statsAverageValue";
import type { StatsMaxValue } from "./statsMaxValue";
import type { StatsMinValue } from "./statsMinValue";

export interface Stats {
  average_value: StatsAverageValue;
  fig_path: string;
  max_value: StatsMaxValue;
  min_value: StatsMinValue;
}
