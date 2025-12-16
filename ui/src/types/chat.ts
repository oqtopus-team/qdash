export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
}

export interface ToolCall {
  function: {
    name: string;
    arguments: Record<string, unknown>;
  };
}

export interface ToolHandler {
  name: string;
  description: string;
  handler: (args: Record<string, unknown>) => Promise<string>;
}

export interface ChatContextData {
  pathname: string;
  metricsData?: Record<string, unknown>;
  chipId?: string;
  metricType?: string;
  selectedMetric?: string;
  timeRange?: string;
}
