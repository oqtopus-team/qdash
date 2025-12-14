import {
  CopilotRuntime,
  OpenAIAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { NextRequest } from "next/server";

import { getCopilotConfig } from "@/client/metrics/metrics";
import type { CopilotConfig } from "@/hooks/useCopilotConfig";

// Create service adapter based on config
function createServiceAdapter(config: CopilotConfig | null) {
  const model = config?.model?.name || "gpt-4o-mini";

  // Currently only OpenAI is supported by CopilotKit runtime
  // Anthropic support would require AnthropicAdapter when available
  return new OpenAIAdapter({ model });
}

export const POST = async (req: NextRequest) => {
  // Fetch config using generated client
  let config: CopilotConfig | null = null;
  try {
    const response = await getCopilotConfig();
    config = response.data as unknown as CopilotConfig;
  } catch {
    // Use default config if fetch fails
  }

  const serviceAdapter = createServiceAdapter(config);
  const runtime = new CopilotRuntime();

  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter,
    endpoint: "/api/copilotkit",
  });

  return handleRequest(req);
};
