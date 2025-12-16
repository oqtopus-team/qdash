"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ChatPopup } from "./ChatPopup";
import {
  AssistantRuntimeProvider,
  registerTool,
  unregisterTool,
} from "./AssistantRuntimeProvider";

export function ChatAssistant() {
  const router = useRouter();
  const pathname = usePathname();

  // Register navigation tools
  useEffect(() => {
    registerTool("navigateTo", async (args) => {
      const path = args.path as string;
      const description = args.description as string | undefined;
      router.push(path);
      return `Navigated to ${description || path}`;
    });

    registerTool("navigateToChip", async (args) => {
      const chipId = args.chipId as string;
      router.push(`/chip?selected=${encodeURIComponent(chipId)}`);
      return `Navigated to chip ${chipId}`;
    });

    registerTool("navigateToQubit", async (args) => {
      const chipId = args.chipId as string;
      const qubitId = args.qubitId as string;
      router.push(
        `/chip/${encodeURIComponent(chipId)}/qubit/${encodeURIComponent(qubitId)}`
      );
      return `Navigated to qubit ${qubitId} on chip ${chipId}`;
    });

    registerTool("navigateToWorkflow", async (args) => {
      const workflowName = args.workflowName as string;
      router.push(`/workflow/${encodeURIComponent(workflowName)}`);
      return `Navigated to workflow ${workflowName}`;
    });

    registerTool("navigateToExecution", async (args) => {
      const chipId = args.chipId as string;
      const executeId = args.executeId as string;
      router.push(
        `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executeId)}`
      );
      return `Navigated to execution ${executeId}`;
    });

    return () => {
      unregisterTool("navigateTo");
      unregisterTool("navigateToChip");
      unregisterTool("navigateToQubit");
      unregisterTool("navigateToWorkflow");
      unregisterTool("navigateToExecution");
    };
  }, [router]);

  return (
    <AssistantRuntimeProvider context={{ pathname }}>
      <ChatPopup />
    </AssistantRuntimeProvider>
  );
}
