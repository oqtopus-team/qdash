"use client";

import { useState } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";

import AxiosProvider from "./providers/AxiosProvider";
import { ThemeProvider } from "./providers/theme-provider";

import { ThemedToastContainer } from "@/components/ui/ThemedToastContainer";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProjectProvider } from "@/contexts/ProjectContext";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <AxiosProvider>
      <QueryClientProvider client={queryClient}>
        <NuqsAdapter>
          <AuthProvider>
            <ProjectProvider>
              <ThemeProvider>
                {children}
                <ThemedToastContainer />
              </ThemeProvider>
            </ProjectProvider>
          </AuthProvider>
        </NuqsAdapter>
      </QueryClientProvider>
    </AxiosProvider>
  );
}
