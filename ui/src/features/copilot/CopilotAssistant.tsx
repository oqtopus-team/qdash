"use client";

import { CopilotPopup } from "@copilotkit/react-ui";
import { useCopilotNavigation } from "./hooks/useCopilotNavigation";

export function CopilotAssistant() {
  // Register navigation actions
  useCopilotNavigation();

  return (
    <CopilotPopup
      labels={{
        title: "QDash Assistant",
        initial:
          "Hi! I can help you navigate QDash. Try asking:\n\n" +
          '- "Show me the metrics dashboard"\n' +
          '- "Go to chip list"\n' +
          '- "Open workflow editor"\n' +
          '- "Where can I see execution results?"',
      }}
      instructions={`You are a navigation assistant for QDash, a qubit calibration management platform.

Your primary job is to help users navigate to different pages in the application.

Available pages:
- /metrics - Main metrics dashboard showing calibration metrics
- /chip - List of all chips
- /chip/[chipId]/qubit/[qubitId] - Specific qubit details (need chipId and qubitId)
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

When users ask to see something, use the navigateTo action to take them there.
Be helpful and concise. If you need more information (like a chip ID), ask for it.`}
    />
  );
}
