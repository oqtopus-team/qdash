/**
 * Generated by orval v7.3.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { TwoQubitCalibHistoryResponseTwoQubitCalibData } from "./twoQubitCalibHistoryResponseTwoQubitCalibData";

export interface TwoQubitCalibHistoryResponse {
  cooling_down_id: number;
  created_at?: string;
  date: string;
  label: string;
  qpu_name: string;
  two_qubit_calib_data: TwoQubitCalibHistoryResponseTwoQubitCalibData;
  updated_at?: string;
}