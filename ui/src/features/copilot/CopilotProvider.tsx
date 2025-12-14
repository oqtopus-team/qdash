"use client";

import { CopilotKit } from "@copilotkit/react-core";
import "@copilotkit/react-ui/styles.css";

interface CopilotProviderProps {
  children: React.ReactNode;
}

export function CopilotProvider({ children }: CopilotProviderProps) {
  return <CopilotKit runtimeUrl="/api/copilotkit">{children}</CopilotKit>;
}
