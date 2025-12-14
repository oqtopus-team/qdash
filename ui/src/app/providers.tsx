"use client";

import { useState } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";

import AxiosProvider from "./providers/AxiosProvider";
import { ThemeProvider } from "./providers/theme-provider";

import { ToastProvider, ToastContainer } from "@/components/ui/Toast";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { COPILOT_ENABLED, CopilotProvider } from "@/features/copilot";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  const content = (
    <AxiosProvider>
      <QueryClientProvider client={queryClient}>
        <NuqsAdapter>
          <AuthProvider>
            <ProjectProvider>
              <ThemeProvider>
                <ToastProvider>
                  {children}
                  <ToastContainer />
                </ToastProvider>
              </ThemeProvider>
            </ProjectProvider>
          </AuthProvider>
        </NuqsAdapter>
      </QueryClientProvider>
    </AxiosProvider>
  );

  // Wrap with CopilotKit only when enabled via feature flag
  if (COPILOT_ENABLED) {
    return <CopilotProvider>{content}</CopilotProvider>;
  }

  return content;
}
