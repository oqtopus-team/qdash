/**
 * Generated by orval v7.3.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { TwoQubitCalibSummary } from "./twoQubitCalibSummary";

export interface TwoQubitCalibDailySummaryRequest {
  cooling_down_id: number;
  date: string;
  labels: string[];
  note?: string;
  qpu_name: string;
  summary: TwoQubitCalibSummary[];
}
