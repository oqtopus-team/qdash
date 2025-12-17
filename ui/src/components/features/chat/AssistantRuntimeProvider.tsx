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

        const data = await response.json();
        const assistantMsg = data.message;

        // Check for tool calls
        if (assistantMsg.tool_calls && assistantMsg.tool_calls.length > 0) {
          // Execute tool calls
          const toolResults: string[] = [];
          for (const toolCall of assistantMsg.tool_calls) {
            const result = await executeTool(
              toolCall.function.name,
              toolCall.function.arguments,
            );
            toolResults.push(`${toolCall.function.name}: ${result}`);
          }

          // Send tool results back and get final response
          const messagesWithTools: OllamaMessage[] = [
            ...apiMessages,
            {
              role: "assistant" as const,
              content: assistantMsg.content || "",
              tool_calls: assistantMsg.tool_calls,
            },
            {
              role: "tool" as const,
              content: toolResults.join("\n"),
            },
          ];

          const followUpResponse = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              messages: messagesWithTools,
              context,
              copilotConfig,
            }),
          });

          if (followUpResponse.ok) {
            const followUpData = await followUpResponse.json();
            const finalMessage: ThreadMessageLike = {
              role: "assistant",
              content: [
                {
                  type: "text",
                  text: followUpData.message.content || toolResults.join("\n"),
                },
              ],
            };
            // Set running to false before adding message to avoid double AI icon
            setIsRunning(false);
            setMessages((currentMessages) => [
              ...currentMessages,
              finalMessage,
            ]);
          } else {
            // If follow-up fails, show tool results
            const toolResultMessage: ThreadMessageLike = {
              role: "assistant",
              content: [{ type: "text", text: toolResults.join("\n") }],
            };
            setIsRunning(false);
            setMessages((currentMessages) => [
              ...currentMessages,
              toolResultMessage,
            ]);
          }
        } else {
          // No tool calls, just add the response
          const assistantMessage: ThreadMessageLike = {
            role: "assistant",
            content: [{ type: "text", text: assistantMsg.content }],
          };
          setIsRunning(false);
          setMessages((currentMessages) => [
            ...currentMessages,
            assistantMessage,
          ]);
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
