"use client";

import { useState } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";

import { AxiosProvider } from "@/contexts/AxiosContext";
import { ThemeProvider } from "@/contexts/ThemeContext";

import { ToastProvider, ToastContainer } from "@/components/ui/Toast";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <NuqsAdapter>
        <AuthProvider>
          <AxiosProvider>
            <ProjectProvider>
              <ThemeProvider>
                <ToastProvider>
                  {children}
                  <ToastContainer />
                </ToastProvider>
              </ThemeProvider>
            </ProjectProvider>
          </AxiosProvider>
        </AuthProvider>
      </NuqsAdapter>
    </QueryClientProvider>
  );
}
