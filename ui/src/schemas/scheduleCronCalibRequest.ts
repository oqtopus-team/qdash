/**
 * Generated by orval v7.7.0 🍺
 * Do not edit manually.
 * QDash API
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */

/**
 * ScheduleCronCalibRequest is a subclass of BaseModel.
 */
export interface ScheduleCronCalibRequest {
  scheduler_name: string;
  menu_name: string;
  cron: string;
  active?: boolean;
}
