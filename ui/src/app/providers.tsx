"use client";

import { useState } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";

import { ThemedToastContainer } from "./components/ThemedToastContainer";
import { AuthProvider } from "./contexts/AuthContext";
import AxiosProvider from "./providers/AxiosProvider";
import { ThemeProvider } from "./providers/theme-provider";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <AxiosProvider>
      <QueryClientProvider client={queryClient}>
        <NuqsAdapter>
          <AuthProvider>
            <ThemeProvider>
              {children}
              <ThemedToastContainer />
            </ThemeProvider>
          </AuthProvider>
        </NuqsAdapter>
      </QueryClientProvider>
    </AxiosProvider>
  );
}
