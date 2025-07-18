/**
 * Generated by orval v7.10.0 🍺
 * Do not edit manually.
 * QDash API
 * API for QDash
 * OpenAPI spec version: 0.0.1
 */
import type { ExecutionResponseSummaryNote } from "./executionResponseSummaryNote";

/**
 * ExecutionResponseSummaryV2 is a Pydantic model that represents the summary of an execution response.

Attributes
----------
    name (str): The name of the execution.
    status (str): The current status of the execution.
    start_at (str): The start time of the execution.
    end_at (str): The end time of the execution.
    elapsed_time (str): The total elapsed time of the execution.
 */
export interface ExecutionResponseSummary {
  name: string;
  execution_id: string;
  status: string;
  start_at: string;
  end_at: string;
  elapsed_time: string;
  tags: string[];
  note: ExecutionResponseSummaryNote;
}
