"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import {
  createContext,
  useCallback,
  useContext,
  useState,
  useEffect,
} from "react";

import type { User } from "@/schemas";

import { useGetCurrentUser, useLogin, useLogout } from "@/client/auth/auth";

interface AuthContextType {
  user: User | null;
  username: string | null;
  accessToken: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Save authentication info
  const saveAuth = useCallback((token: string, user: string) => {
    const maxAge = 365 * 24 * 60 * 60; // 1 year (long-term token)
    // Save access token and username cookies
    document.cookie = `access_token=${encodeURIComponent(
      token,
    )}; path=/; max-age=${maxAge}; SameSite=Lax`;
    document.cookie = `username=${encodeURIComponent(
      user,
    )}; path=/; max-age=${maxAge}; SameSite=Lax`;
    setAccessToken(token);
    setUsername(user);
  }, []);

  // Remove authentication info
  const removeAuth = useCallback(() => {
    // Remove access token and username cookies
    document.cookie =
      "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    document.cookie =
      "username=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    setAccessToken(null);
    setUsername(null);
  }, []);

  // Login mutation
  const loginMutation = useLogin();

  // Logout mutation
  const logoutMutation = useLogout();

  // Get user info
  const { data: userData, error: userError } = useGetCurrentUser({
    query: {
      enabled: !!accessToken,
      retry: false,
    },
  });

  // Update user info
  useEffect(() => {
    if (userData?.data) {
      setUser(userData.data);
    }
  }, [userData]);

  // Handle errors
  useEffect(() => {
    if (userError) {
      console.error("Failed to fetch user info:", userError);
      removeAuth();
      setUser(null);
    }
  }, [userError, removeAuth]);

  // Initialization
  useEffect(() => {
    const token = document.cookie
      .split("; ")
      .find((row) => row.startsWith("access_token="))
      ?.split("=")[1];

    const user = document.cookie
      .split("; ")
      .find((row) => row.startsWith("username="))
      ?.split("=")[1];

    if (token && user) {
      try {
        const decodedToken = decodeURIComponent(token);
        const decodedUser = decodeURIComponent(user);
        setAccessToken(decodedToken);
        setUsername(decodedUser);
      } catch (error) {
        console.error("Failed to decode token:", error);
        removeAuth();
      }
    }
    setLoading(false);
  }, [removeAuth]);

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

        // Save auth info (access_token and username)
        saveAuth(response.data.access_token, response.data.username);

        // Redirect immediately
        router.replace("/execution");
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
    [loginMutation, saveAuth, router, removeAuth],
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
      value={{ user, username, accessToken, login, logout, loading }}
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
