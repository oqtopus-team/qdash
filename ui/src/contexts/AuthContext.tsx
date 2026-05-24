"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useState, useEffect } from "react";
import Axios from "axios";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";

import type { User } from "@/schemas";

import { useGetCurrentUser, useLogin } from "@/client/auth/auth";

interface AuthContextType {
  user: User | null;
  username: string | null;
  isAuthenticated: boolean;
  accessToken: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function isAuthenticationError(error: unknown): boolean {
  if (!Axios.isAxiosError(error)) {
    return false;
  }
  const status = error.response?.status;
  return status === 401 || status === 403;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const isPublicAuthRoute =
    pathname === "/login" || pathname === "/signup" || pathname === "/logout";
  const [user, setUser] = useState<User | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Save authentication info
  const saveAuth = useCallback((user: string) => {
    setUsername(user);
  }, []);

  // Remove authentication info
  const removeAuth = useCallback(() => {
    setUsername(null);
  }, []);

  const clearServerSession = useCallback(() => {
    void fetch("/api/auth/logout", { method: "POST" }).catch((error: unknown) => {
      console.warn("Failed to clear server session:", error);
    });
  }, []);

  // Login mutation
  const loginMutation = useLogin();

  // Get user info
  const { data: userData, error: userError } = useGetCurrentUser({
    query: {
      enabled: !isPublicAuthRoute,
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      staleTime: 5 * 60 * 1000,
    },
  });

  // Update user info
  useEffect(() => {
    if (userData?.data) {
      setUser(userData.data);
      setUsername(userData.data.username);
      setLoading(false);
    }
  }, [userData]);

  // Handle errors
  useEffect(() => {
    if (userError) {
      if (isAuthenticationError(userError)) {
        removeAuth();
        clearServerSession();
        setUser(null);
      } else {
        console.error("Failed to fetch user info:", userError);
      }
      setLoading(false);
    }
  }, [userError, clearServerSession, removeAuth]);

  // Initialization
  useEffect(() => {
    if (isPublicAuthRoute) {
      setLoading(false);
      return;
    }
    if (userData || userError) {
      setLoading(false);
    }
  }, [isPublicAuthRoute, userData, userError]);

  const login = useCallback(
    async (username: string, password: string) => {
      try {
        setLoading(true); // Start loading
        const response = await loginMutation.mutateAsync({
          data: {
            username,
            password,
          },
        });

        // The API route stores the session token in an HttpOnly cookie.
        saveAuth(response.data.username);
      } catch (error) {
        console.error("Login failed:", error);
        // Clear auth info
        removeAuth();
        setUser(null);
        throw error;
      } finally {
        setLoading(false); // End loading
      }
    },
    [loginMutation, saveAuth, removeAuth],
  );

  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
      });
      await queryClient.clear();
      loginMutation.reset();
      // Clear state
      setUser(null);
      // Remove auth info (middleware will handle redirect automatically)
      removeAuth();
      // Explicitly navigate to login page
      window.location.href = "/logout";
    } catch (error) {
      console.error("Logout failed:", error);
      // Same handling on error
      setUser(null);
      removeAuth();
      window.location.href = "/logout";
    }
  }, [loginMutation, queryClient, removeAuth]);

  return (
    <AuthContext.Provider
      value={{
        user,
        username,
        isAuthenticated: !!user,
        accessToken: null,
        login,
        logout,
        loading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
