export interface MetricHistoryItem {
  value: number | null;
  execution_id: string;
  task_id: string | null;
  timestamp: string;
  calibrated_at: string | null;
  name: string | null;
  input_parameters: Record<string, unknown> | null;
  output_parameters: Record<string, unknown> | null;
}
