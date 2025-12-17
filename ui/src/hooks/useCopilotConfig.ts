/**
 * Custom hook for loading Copilot configuration from backend.
 *
 * This hook wraps the auto-generated useGetCopilotConfig hook and provides
 * a consistent interface with typed configuration.
 */

import { useGetCopilotConfig } from "@/client/copilot/copilot";

export interface ScoringThreshold {
  good: number;
  excellent: number;
  unit: string;
  higher_is_better: boolean;
}

export interface EvaluationMetrics {
  qubit: string[];
  coupling: string[];
}

export interface ModelConfig {
  provider: "openai" | "anthropic";
  name: string;
  temperature: number;
  max_tokens: number;
}

export interface CopilotConfig {
  enabled: boolean;
  model: ModelConfig;
  evaluation_metrics: EvaluationMetrics;
  scoring: Record<string, ScoringThreshold>;
  system_prompt: string;
  initial_message: string;
}

/**
 * Hook to load and parse Copilot configuration.
 *
 * @returns Object containing:
 *   - config: The Copilot configuration
 *   - isLoading: Loading state
 *   - isError: Error state
 *   - error: Error object if failed
 */
export function useCopilotConfig() {
  const { data, isLoading, isError, error } = useGetCopilotConfig({
    query: {
      staleTime: Infinity, // Config rarely changes, cache indefinitely
      gcTime: Infinity, // Keep in cache forever
    },
  });

  // The generated client returns the response data directly
  // Cast to CopilotConfig since the backend returns dict[str, Any]
  return {
    config: data ? (data.data as unknown as CopilotConfig) : null,
    isLoading,
    isError,
    error,
  };
}
