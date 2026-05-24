"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useState, useEffect } from "react";
import Axios from "axios";

import type { User } from "@/schemas";

import { useGetCurrentUser, useLogin, useLogout } from "@/client/auth/auth";

interface AuthContextType {
  user: User | null;
  username: string | null;
  isAuthenticated: boolean;
  accessToken: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
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

  // Logout mutation
  const logoutMutation = useLogout();

  // Get user info
  const {
    data: userData,
    error: userError,
    refetch: refetchCurrentUser,
  } = useGetCurrentUser({
    query: {
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
    if (userData || userError) {
      setLoading(false);
    }
  }, [userData, userError]);

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
        await refetchCurrentUser();
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
    [loginMutation, refetchCurrentUser, saveAuth, removeAuth],
  );

  const logout = useCallback(async () => {
    try {
      // Call logout API first
      await logoutMutation.mutateAsync();
      // Clear cache
      await Promise.all([loginMutation.reset(), logoutMutation.reset()]);
      // Clear state
      setUser(null);
      // Remove auth info (middleware will handle redirect automatically)
      removeAuth();
      // Explicitly navigate to login page
      window.location.href = "/login";
    } catch (error) {
      console.error("Logout failed:", error);
      // Same handling on error
      setUser(null);
      removeAuth();
      window.location.href = "/login";
    }
  }, [logoutMutation, removeAuth, loginMutation]);

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
