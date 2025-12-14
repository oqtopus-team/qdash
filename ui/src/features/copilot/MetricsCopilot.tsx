"use client";

import { useState } from "react";
import { CopilotChat } from "@copilotkit/react-ui";
import { MessageSquare, X, ChevronLeft, ChevronRight } from "lucide-react";

import type { CopilotConfig } from "@/hooks/useCopilotConfig";

interface MetricsCopilotProps {
  className?: string;
  aiConfig?: CopilotConfig | null;
}

// Default messages when config is not available
const DEFAULT_INITIAL_MESSAGE =
  "I can help you evaluate this chip using multiple metrics (T1, T2, fidelity, etc.).\n\n" +
  "Try asking:\n" +
  '- "Evaluate this chip\'s overall health"\n' +
  '- "Which qubits have problems?"\n' +
  '- "Are there qubits with both low T1 and T2?"\n' +
  '- "Summarize the chip quality"';

const DEFAULT_SYSTEM_PROMPT = `You are an expert quantum computing analyst helping users evaluate qubit chip performance through multi-metric analysis.

## Your Capabilities
1. **Multi-metric evaluation**: Analyze T1, T2_echo, T2_ramsey, gate fidelity, readout fidelity together
2. **Chip health assessment**: Provide overall chip quality ratings based on combined metrics
3. **Problem identification**: Find qubits with issues across multiple metrics
4. **Comparative analysis**: Compare metrics distributions and identify correlations

## Response Guidelines
- Start with overall chip health when asked for evaluation
- Highlight qubits that have issues in MULTIPLE metrics (these need attention)
- Use the actual data - don't make up values
- Include units when discussing values
- Be concise but actionable

Always respond in the same language the user uses (Japanese or English).`;

export function MetricsCopilot({
  className = "",
  aiConfig,
}: MetricsCopilotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className={`btn btn-primary btn-circle shadow-lg ${className}`}
        title="Open AI Assistant"
      >
        <MessageSquare className="w-5 h-5" />
      </button>
    );
  }

  return (
    <div
      className={`flex flex-col bg-base-100 border border-base-300 rounded-lg shadow-xl overflow-hidden transition-all duration-300 ${
        isExpanded ? "w-[500px]" : "w-[380px]"
      } h-[600px] ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-base-200 border-b border-base-300">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-primary" />
          <span className="font-semibold">Metrics Analysis Assistant</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="btn btn-ghost btn-xs btn-square"
            title={isExpanded ? "Collapse" : "Expand"}
          >
            {isExpanded ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="btn btn-ghost btn-xs btn-square"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Chat */}
      <div className="flex-1 overflow-hidden">
        <CopilotChat
          className="h-full"
          labels={{
            initial: aiConfig?.initial_message || DEFAULT_INITIAL_MESSAGE,
          }}
          instructions={aiConfig?.system_prompt || DEFAULT_SYSTEM_PROMPT}
        />
      </div>
    </div>
  );
}
