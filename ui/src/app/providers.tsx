"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { AuthProvider } from "./contexts/AuthContext";
import { ThemeProvider } from "./providers/theme-provider";
import { ThemedToastContainer } from "./components/ThemedToastContainer";
import AxiosProvider from "./providers/AxiosProvider";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <AxiosProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ThemeProvider>
            {children}
            <ThemedToastContainer />
          </ThemeProvider>
        </AuthProvider>
      </QueryClientProvider>
    </AxiosProvider>
  );
}
