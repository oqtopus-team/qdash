"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import {
  useAuthReadUsersMe,
  useAuthLoginForAccessToken,
  useAuthLogout,
} from "@/client/auth/auth";
import type { User } from "../../schemas";
import axios, { AxiosRequestConfig } from "axios";

interface AuthContextType {
  user: User | null;
  username: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // ユーザー名の保存
  const saveUsername = useCallback((username: string) => {
    const encodedUsername = encodeURIComponent(username);
    document.cookie = `username=${encodedUsername}; path=/; max-age=${
      7 * 24 * 60 * 60
    }; SameSite=Lax`;
    setUsername(username);
  }, []);

  // ユーザー名の削除
  const removeUsername = useCallback(() => {
    document.cookie =
      "username=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    setUsername(null);
  }, []);

  // ログイン処理
  const loginMutation = useAuthLoginForAccessToken();

  // ログアウト処理
  const logoutMutation = useAuthLogout();

  // ユーザー情報の取得
  const { data: userData, error: userError } = useAuthReadUsersMe({
    query: {
      enabled: !!username,
      retry: false,
    },
    axios: {
      headers: username ? { "X-Username": username } : undefined,
    } as AxiosRequestConfig,
  });

  // ユーザー情報の更新
  useEffect(() => {
    if (userData?.data) {
      setUser(userData.data);
    }
  }, [userData]);

  // エラー時の処理
  useEffect(() => {
    if (userError) {
      console.error("Failed to fetch user info:", userError);
      removeUsername();
      setUser(null);
    }
  }, [userError, removeUsername]);

  // 初期化処理
  useEffect(() => {
    const storedUsername = document.cookie
      .split("; ")
      .find((row) => row.startsWith("username="))
      ?.split("=")[1];

    if (storedUsername) {
      try {
        const decodedUsername = decodeURIComponent(storedUsername);
        setUsername(decodedUsername);
      } catch (error) {
        console.error("Failed to decode username:", error);
        removeUsername();
      }
    }
    setLoading(false);
  }, [removeUsername]);

  const login = useCallback(
    async (username: string, password: string) => {
      try {
        const response = await loginMutation.mutateAsync({
          data: {
            username,
            password,
            grant_type: "password",
          },
        });
        // トークンとユーザー名を保存
        const token = response.data.access_token;
        document.cookie = `token=${encodeURIComponent(
          token
        )}; path=/; max-age=${7 * 24 * 60 * 60}; SameSite=Lax`;
        saveUsername(username);
      } catch (error) {
        console.error("Login failed:", error);
        throw error;
      }
    },
    [loginMutation, saveUsername]
  );

  const logout = useCallback(async () => {
    try {
      await logoutMutation.mutateAsync();
      // すべての状態をクリア
      setUser(null);
      removeUsername();
      // トークンを削除
      document.cookie =
        "token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
      // キャッシュをクリア
      await Promise.all([loginMutation.reset(), logoutMutation.reset()]);
      // ページをリロードしてすべての状態をリセット
      // クエリパラメータなしでリダイレクト
      window.location.replace("/login");
    } catch (error) {
      console.error("Logout failed:", error);
      // エラーが発生しても状態をクリーンアップ
      setUser(null);
      removeUsername();
      document.cookie =
        "token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
      // クエリパラメータなしでリダイレクト
      window.location.replace("/login");
    }
  }, [logoutMutation, removeUsername, loginMutation]);

  return (
    <AuthContext.Provider value={{ user, username, login, logout, loading }}>
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
