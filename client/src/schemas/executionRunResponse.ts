/**
 * Generated by orval v7.3.0 🍺
 * Do not edit manually.
 * QDash Server
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { ExecutionRunResponseFlowUrl } from "./executionRunResponseFlowUrl";
import type { ExecutionRunResponseFridgeTemperature } from "./executionRunResponseFridgeTemperature";
import type { ExecutionRunResponseMenu } from "./executionRunResponseMenu";
import type { ExecutionRunResponseQpuName } from "./executionRunResponseQpuName";
import type { ExecutionRunResponseStatus } from "./executionRunResponseStatus";
import type { ExecutionRunResponseTags } from "./executionRunResponseTags";

export interface ExecutionRunResponse {
  date: string;
  execution_id: string;
  flow_url?: ExecutionRunResponseFlowUrl;
  fridge_temperature?: ExecutionRunResponseFridgeTemperature;
  menu: ExecutionRunResponseMenu;
  qpu_name?: ExecutionRunResponseQpuName;
  status?: ExecutionRunResponseStatus;
  tags?: ExecutionRunResponseTags;
  timestamp: string;
}