"use client";

import { useState, useCallback, type ReactNode } from "react";
import {
  AssistantRuntimeProvider as BaseAssistantRuntimeProvider,
  useExternalStoreRuntime,
  type ThreadMessageLike,
  type AppendMessage,
} from "@assistant-ui/react";

interface OllamaMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: Array<{
    function: {
      name: string;
      arguments: Record<string, unknown>;
    };
  }>;
}

interface ChatContext {
  pathname?: string;
  chipId?: string;
  metricType?: string;
  selectedMetric?: string;
  timeRange?: string;
  metricsData?: Record<string, unknown>;
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

// Tool handlers registry
type ToolHandler = (args: Record<string, unknown>) => Promise<string>;
const toolHandlers = new Map<string, ToolHandler>();

export function registerTool(name: string, handler: ToolHandler) {
  toolHandlers.set(name, handler);
}

export function unregisterTool(name: string) {
  toolHandlers.delete(name);
}

async function executeTool(
  name: string,
  args: Record<string, unknown>,
): Promise<string> {
  const handler = toolHandlers.get(name);
  if (!handler) {
    return `Tool "${name}" not found`;
  }
  try {
    return await handler(args);
  } catch (error) {
    return `Error executing tool: ${error instanceof Error ? error.message : "Unknown error"}`;
  }
}

const convertMessage = (message: ThreadMessageLike): ThreadMessageLike => {
  return message;
};

interface AssistantRuntimeProviderProps {
  children: ReactNode;
  context?: ChatContext;
  copilotConfig?: CopilotConfig;
}

export function AssistantRuntimeProvider({
  children,
  context,
  copilotConfig,
}: AssistantRuntimeProviderProps) {
  const [messages, setMessages] = useState<readonly ThreadMessageLike[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const onNew = useCallback(
    async (message: AppendMessage) => {
      if (message.content.length !== 1 || message.content[0]?.type !== "text") {
        throw new Error("Only text content is supported");
      }

      const userMessage: ThreadMessageLike = {
        role: "user",
        content: [{ type: "text", text: message.content[0].text }],
      };

      setMessages((currentMessages) => [...currentMessages, userMessage]);
      setIsRunning(true);

      try {
        // Convert ThreadMessageLike to API format
        const apiMessages: OllamaMessage[] = [...messages, userMessage].map(
          (m) => ({
            role: m.role as OllamaMessage["role"],
            content:
              typeof m.content === "string"
                ? m.content
                : m.content
                    ?.map((c) => (c.type === "text" ? c.text : ""))
                    .join("") || "",
          }),
        );

        // Call Ollama API
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: apiMessages,
            context,
            copilotConfig,
          }),
        });

        if (!response.ok) {
          throw new Error(`API error: ${response.status}`);
        }

        let currentData = await response.json();
        let currentMsg = currentData.message;
        let currentMessages = [...apiMessages];
        const maxToolRounds = 5; // Prevent infinite loops
        let toolRound = 0;

        // Loop to handle multiple rounds of tool calls
        while (
          currentMsg.tool_calls &&
          currentMsg.tool_calls.length > 0 &&
          toolRound < maxToolRounds
        ) {
          toolRound++;
          console.log(`Tool round ${toolRound}:`, currentMsg.tool_calls);

          // Execute tool calls
          const toolResults: string[] = [];
          for (const toolCall of currentMsg.tool_calls) {
            console.log(
              "Executing tool:",
              toolCall.function.name,
              toolCall.function.arguments,
            );
            const result = await executeTool(
              toolCall.function.name,
              toolCall.function.arguments,
            );
            console.log("Tool result:", result.substring(0, 200) + "...");
            toolResults.push(`${toolCall.function.name}: ${result}`);
          }

          // Add assistant message and tool results to conversation
          currentMessages = [
            ...currentMessages,
            {
              role: "assistant" as const,
              content: currentMsg.content || "",
              tool_calls: currentMsg.tool_calls,
            },
            {
              role: "tool" as const,
              content: toolResults.join("\n"),
            },
          ];

          // Send follow-up request
          console.log(`Sending follow-up request (round ${toolRound})`);
          const followUpResponse = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              messages: currentMessages,
              context,
              copilotConfig,
            }),
          });

          if (!followUpResponse.ok) {
            // If follow-up fails, show tool results collected so far
            const toolResultMessage: ThreadMessageLike = {
              role: "assistant",
              content: [{ type: "text", text: toolResults.join("\n") }],
            };
            setIsRunning(false);
            setMessages((prev) => [...prev, toolResultMessage]);
            return;
          }

          currentData = await followUpResponse.json();
          currentMsg = currentData.message;
          console.log(
            "Follow-up response has tool_calls:",
            !!(currentMsg.tool_calls && currentMsg.tool_calls.length > 0),
          );
        }

        // Final response (no more tool calls)
        if (currentMsg.content) {
          const finalMessage: ThreadMessageLike = {
            role: "assistant",
            content: [{ type: "text", text: currentMsg.content }],
          };
          setIsRunning(false);
          setMessages((prev) => [...prev, finalMessage]);
        } else if (toolRound > 0) {
          // If we had tool calls but no final content, show last tool results
          const lastToolMsg = currentMessages[currentMessages.length - 1];
          const finalMessage: ThreadMessageLike = {
            role: "assistant",
            content: [
              {
                type: "text",
                text:
                  typeof lastToolMsg.content === "string"
                    ? lastToolMsg.content
                    : "Tool execution completed.",
              },
            ],
          };
          setIsRunning(false);
          setMessages((prev) => [...prev, finalMessage]);
        } else {
          // No tool calls and no content - shouldn't happen, but handle gracefully
          const assistantMessage: ThreadMessageLike = {
            role: "assistant",
            content: [
              {
                type: "text",
                text: currentMsg.content || "No response generated.",
              },
            ],
          };
          setIsRunning(false);
          setMessages((prev) => [...prev, assistantMessage]);
        }
      } catch (error) {
        console.error("Chat error:", error);
        const errorMessage: ThreadMessageLike = {
          role: "assistant",
          content: [
            {
              type: "text",
              text: `Error: ${error instanceof Error ? error.message : "Failed to send message"}`,
            },
          ],
        };
        setIsRunning(false);
        setMessages((currentMessages) => [...currentMessages, errorMessage]);
      }
    },
    [messages, context, copilotConfig],
  );

  const runtime = useExternalStoreRuntime({
    isRunning,
    messages,
    setMessages,
    onNew,
    convertMessage,
  });

  return (
    <BaseAssistantRuntimeProvider runtime={runtime}>
      {children}
    </BaseAssistantRuntimeProvider>
  );
}
