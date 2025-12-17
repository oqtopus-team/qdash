import { NextRequest, NextResponse } from "next/server";
import { Ollama, type Tool } from "ollama";

export const runtime = "nodejs";

interface Message {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: ToolCall[];
}

interface ToolCall {
  function: {
    name: string;
    arguments: Record<string, unknown>;
  };
}

interface CopilotConfig {
  system_prompt?: string;
  model?: {
    provider?: string;
    name?: string;
    temperature?: number;
    max_tokens?: number;
  };
}

// Tool definitions for QDash
const TOOLS: Tool[] = [
  {
    type: "function",
    function: {
      name: "navigateTo",
      description:
        "Navigate to a specific page in QDash. Use this when users want to go to a page, see something, or open a feature.",
      parameters: {
        type: "object",
        properties: {
          path: {
            type: "string",
            description:
              "The URL path to navigate to (e.g., '/metrics', '/chip', '/workflow')",
          },
          description: {
            type: "string",
            description: "Brief description of where we're navigating",
          },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "navigateToChip",
      description:
        "Navigate to a specific chip's page to see its qubits and details",
      parameters: {
        type: "object",
        properties: {
          chipId: {
            type: "string",
            description: "The chip ID (e.g., 'chip_01', 'FLAVOR01')",
          },
        },
        required: ["chipId"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "navigateToQubit",
      description: "Navigate to a specific qubit's detail page",
      parameters: {
        type: "object",
        properties: {
          chipId: {
            type: "string",
            description: "The chip ID",
          },
          qubitId: {
            type: "string",
            description: "The qubit ID (e.g., 'Q00', 'Q01')",
          },
        },
        required: ["chipId", "qubitId"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "navigateToWorkflow",
      description: "Navigate to a specific workflow's editor page",
      parameters: {
        type: "object",
        properties: {
          workflowName: {
            type: "string",
            description: "The workflow name",
          },
        },
        required: ["workflowName"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "navigateToExecution",
      description: "Navigate to a specific execution's detail page",
      parameters: {
        type: "object",
        properties: {
          chipId: {
            type: "string",
            description: "The chip ID",
          },
          executeId: {
            type: "string",
            description: "The execution ID",
          },
        },
        required: ["chipId", "executeId"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "changeMetric",
      description: "Change the currently displayed metric on the metrics page",
      parameters: {
        type: "object",
        properties: {
          metricKey: {
            type: "string",
            description:
              "The metric key to switch to (e.g., 't1', 't2_echo', 'average_gate_fidelity')",
          },
        },
        required: ["metricKey"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "changeTimeRange",
      description: "Change the time range for metrics data",
      parameters: {
        type: "object",
        properties: {
          range: {
            type: "string",
            description:
              "Time range: '1d' for last day, '7d' for last week, '30d' for last month",
          },
        },
        required: ["range"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "getChipList",
      description:
        "Fetch the list of all available chips in the system. Use this to find what chips exist before analyzing metrics.",
      parameters: {
        type: "object",
        properties: {},
        required: [],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "getChipMetricsData",
      description:
        "Fetch calibration metrics data for a chip. Returns statistics for T1, T2, gate fidelity, readout fidelity. If no chipId is specified, uses the latest chip. Default time range is 7 days.",
      parameters: {
        type: "object",
        properties: {
          chipId: {
            type: "string",
            description:
              "The chip ID to fetch metrics for. If not specified, uses the latest chip.",
          },
          withinHours: {
            type: "number",
            description:
              "Time range in hours (e.g., 24 for 1 day, 168 for 7 days). Defaults to 168 (7 days).",
          },
        },
        required: [],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "getMetricsConfiguration",
      description:
        "Get the list of available metrics types (qubit and coupling metrics)",
      parameters: {
        type: "object",
        properties: {},
        required: [],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "getChipTopology",
      description:
        "Get the topology (qubit positions, coupling pairs, neighbor map) for a chip. Use this for spatial analysis of metrics, identifying crosstalk candidates, and reasoning about frequency crowding among neighbors.",
      parameters: {
        type: "object",
        properties: {
          chipId: {
            type: "string",
            description:
              "The chip ID to fetch topology for. If not specified or 'latest', uses the latest chip.",
          },
        },
        required: [],
      },
    },
  },
];

// Default system prompt (fallback if config is unavailable)
const DEFAULT_SYSTEM_PROMPT = `You are QDash Assistant, a helpful AI for the QDash qubit calibration management platform.

Your capabilities:
1. Navigate users to different pages in the application
2. Fetch and analyze metrics data autonomously
3. Answer questions about quantum computing and calibration

Data fetching tools:
- Use getChipList to find available chips
- Use getChipMetricsData to fetch metrics (defaults to latest chip, 7 days of data)
- Use getMetricsConfiguration to see available metric types
- Use getChipTopology to get chip topology (qubit positions, couplings, neighbor map) for spatial analysis

IMPORTANT: When users ask to "evaluate", "analyze", or "check" chip metrics without specifying a chip:
- Use getChipMetricsData without arguments to get the latest chip's metrics for 7 days
- Provide a summary with T1, T2, gate fidelity, and readout fidelity statistics
- Highlight any concerning values or trends

Available pages:
- /metrics - Main metrics dashboard showing calibration metrics
- /chip - List of all chips
- /chip?selected=[chipId] - View a specific chip
- /chip/[chipId]/qubit/[qubitId] - Specific qubit details
- /execution - List of all workflow executions
- /execution/[chipId]/[executeId] - Specific execution details
- /workflow - List of all workflows
- /workflow/new - Create a new workflow
- /workflow/[name] - Edit a specific workflow
- /analysis - Data analysis page
- /tasks - Background tasks
- /files - File management
- /setting - Settings page
- /admin - Admin page

When users ask to see something or go somewhere, use the navigation tools.
Be helpful, concise, and technical when needed.`;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages, context, copilotConfig } = body as {
      messages: Message[];
      context?: Record<string, unknown>;
      copilotConfig?: CopilotConfig;
    };

    const ollamaUrl =
      process.env.OLLAMA_URL || "http://host.docker.internal:11434";
    // Use model from config (passed from client), fallback to env var, then default
    const modelName =
      copilotConfig?.model?.name || process.env.OLLAMA_MODEL || "gpt-oss:20b";

    const ollama = new Ollama({ host: ollamaUrl });

    // Use system prompt from config or fallback to default
    let systemMessage = copilotConfig?.system_prompt || DEFAULT_SYSTEM_PROMPT;

    if (context) {
      systemMessage += `\n\nCurrent context:\n${JSON.stringify(context, null, 2)}`;
    }

    // Prepare messages for Ollama
    const ollamaMessages = [
      { role: "system" as const, content: systemMessage },
      ...messages.map((m) => ({
        role: m.role as "user" | "assistant" | "system" | "tool",
        content: m.content,
        ...(m.tool_calls && { tool_calls: m.tool_calls }),
      })),
    ];

    // Call Ollama with tools
    const response = await ollama.chat({
      model: modelName,
      messages: ollamaMessages,
      tools: TOOLS,
      stream: false,
    });

    // Return the response
    return NextResponse.json({
      message: response.message,
      done: true,
    });
  } catch (error) {
    console.error("Chat API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 },
    );
  }
}
