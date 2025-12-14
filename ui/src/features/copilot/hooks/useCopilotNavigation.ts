"use client";

import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { useRouter, usePathname } from "next/navigation";

/**
 * Hook to register navigation-related Copilot actions
 */
export function useCopilotNavigation() {
  const router = useRouter();
  const pathname = usePathname();

  // Provide current location context to the AI
  useCopilotReadable({
    description: "Current page path the user is viewing",
    value: pathname,
  });

  // Main navigation action
  useCopilotAction({
    name: "navigateTo",
    description:
      "Navigate to a specific page in QDash. Use this when users want to go to a page, see something, or open a feature.",
    parameters: [
      {
        name: "path",
        type: "string",
        description:
          "The URL path to navigate to (e.g., '/metrics', '/chip', '/workflow')",
        required: true,
      },
      {
        name: "description",
        type: "string",
        description: "Brief description of where we're navigating",
        required: false,
      },
    ],
    handler: async ({ path, description }) => {
      router.push(path);
      return `Navigated to ${description || path}`;
    },
  });

  // Navigate to specific chip
  useCopilotAction({
    name: "navigateToChip",
    description:
      "Navigate to a specific chip's page to see its qubits and details",
    parameters: [
      {
        name: "chipId",
        type: "string",
        description: "The chip ID (e.g., 'chip_01', 'FLAVOR01')",
        required: true,
      },
    ],
    handler: async ({ chipId }) => {
      router.push(`/chip?selected=${encodeURIComponent(chipId)}`);
      return `Navigated to chip ${chipId}`;
    },
  });

  // Navigate to specific qubit
  useCopilotAction({
    name: "navigateToQubit",
    description: "Navigate to a specific qubit's detail page",
    parameters: [
      {
        name: "chipId",
        type: "string",
        description: "The chip ID",
        required: true,
      },
      {
        name: "qubitId",
        type: "string",
        description: "The qubit ID (e.g., 'Q00', 'Q01')",
        required: true,
      },
    ],
    handler: async ({ chipId, qubitId }) => {
      router.push(
        `/chip/${encodeURIComponent(chipId)}/qubit/${encodeURIComponent(qubitId)}`,
      );
      return `Navigated to qubit ${qubitId} on chip ${chipId}`;
    },
  });

  // Navigate to specific workflow
  useCopilotAction({
    name: "navigateToWorkflow",
    description: "Navigate to a specific workflow's editor page",
    parameters: [
      {
        name: "workflowName",
        type: "string",
        description: "The workflow name",
        required: true,
      },
    ],
    handler: async ({ workflowName }) => {
      router.push(`/workflow/${encodeURIComponent(workflowName)}`);
      return `Navigated to workflow ${workflowName}`;
    },
  });

  // Navigate to specific execution
  useCopilotAction({
    name: "navigateToExecution",
    description: "Navigate to a specific execution's detail page",
    parameters: [
      {
        name: "chipId",
        type: "string",
        description: "The chip ID",
        required: true,
      },
      {
        name: "executeId",
        type: "string",
        description: "The execution ID",
        required: true,
      },
    ],
    handler: async ({ chipId, executeId }) => {
      router.push(
        `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executeId)}`,
      );
      return `Navigated to execution ${executeId}`;
    },
  });
}
