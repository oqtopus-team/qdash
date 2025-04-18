/**
 * Generated by orval v7.8.0 🍺
 * Do not edit manually.
 * QDash API
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { ExecuteCalibRequestSchedule } from "./executeCalibRequestSchedule";
import type { ExecuteCalibRequestTasks } from "./executeCalibRequestTasks";
import type { ExecuteCalibRequestTaskDetails } from "./executeCalibRequestTaskDetails";
import type { ExecuteCalibRequestTags } from "./executeCalibRequestTags";

/**
 * ExecuteCalibRequest is a subclass of MenuModel.
 */
export interface ExecuteCalibRequest {
  name: string;
  username: string;
  description: string;
  schedule: ExecuteCalibRequestSchedule;
  notify_bool?: boolean;
  tasks?: ExecuteCalibRequestTasks;
  task_details?: ExecuteCalibRequestTaskDetails;
  tags?: ExecuteCalibRequestTags;
}
