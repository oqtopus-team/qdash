// Feature flag for CopilotKit integration
// Set NEXT_PUBLIC_COPILOT_ENABLED=true in .env.local to enable
export const COPILOT_ENABLED =
  process.env.NEXT_PUBLIC_COPILOT_ENABLED === "true";

// Re-export components for easy imports
export { CopilotProvider } from "./CopilotProvider";
export { CopilotAssistant } from "./CopilotAssistant";
export { MetricsCopilot } from "./MetricsCopilot";
export { useMetricsCopilot } from "./hooks/useMetricsCopilot";
