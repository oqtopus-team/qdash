/**
 * Generated by orval v7.3.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { ExecuteCalibRequest } from "./executeCalibRequest";

export interface ScheduleCalibResponse {
  description: string;
  flow_run_id: string;
  menu: ExecuteCalibRequest;
  menu_name: string;
  note: string;
  scheduled_time: string;
  timezone: string;
}
