/**
 * Generated by orval v7.6.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { TwoQubitCalibSummary } from "./twoQubitCalibSummary";

export interface TwoQubitCalibDailySummaryRequest {
  date: string;
  labels: string[];
  qpu_name: string;
  cooling_down_id: number;
  summary: TwoQubitCalibSummary[];
  note?: string;
}
