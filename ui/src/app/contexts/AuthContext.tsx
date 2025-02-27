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
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // トークンの保存
  const saveToken = useCallback((token: string) => {
    const encodedToken = encodeURIComponent(token);
    document.cookie = `token=${encodedToken}; path=/; max-age=${
      7 * 24 * 60 * 60
    }; SameSite=Lax`;
    setToken(token);
  }, []);

  // トークンの削除
  const removeToken = useCallback(() => {
    document.cookie =
      "token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    setToken(null);
  }, []);

  // ログイン処理
  const loginMutation = useAuthLoginForAccessToken();

  // ログアウト処理
  const logoutMutation = useAuthLogout();

  // ユーザー情報の取得
  const { data: userData, error: userError } = useAuthReadUsersMe({
    query: {
      enabled: !!token,
      retry: false,
    },
    axios: {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    } as AxiosRequestConfig,
  });

  // ユーザー情報の更新とヘッダーの設定
  useEffect(() => {
    if (userData?.data) {
      const username = userData.data.username;
      setUser(userData.data);
      // グローバルにヘッダーを設定
      window.localStorage.setItem("X-User-ID", username);
      // axiosのデフォルトヘッダーを設定
      axios.defaults.headers.common["X-User-ID"] = username;
    }
  }, [userData]);

  // エラー時の処理
  useEffect(() => {
    if (userError) {
      console.error("Failed to fetch user info:", userError);
      removeToken();
      setUser(null);
      // ユーザーIDをクリア
      window.localStorage.removeItem("X-User-ID");
      delete axios.defaults.headers.common["X-User-ID"];
    }
  }, [userError, removeToken]);

  // 初期化処理
  useEffect(() => {
    const storedToken = document.cookie
      .split("; ")
      .find((row) => row.startsWith("token="))
      ?.split("=")[1];

    const storedUserId = window.localStorage.getItem("X-User-ID");
    if (storedUserId) {
      axios.defaults.headers.common["X-User-ID"] = storedUserId;
    }

    if (storedToken) {
      try {
        const decodedToken = decodeURIComponent(storedToken);
        setToken(decodedToken);
      } catch (error) {
        console.error("Failed to decode token:", error);
        removeToken();
        // ユーザーIDをクリア
        window.localStorage.removeItem("X-User-ID");
        delete axios.defaults.headers.common["X-User-ID"];
      }
    }
    setLoading(false);
  }, [removeToken]);

  const login = useCallback(
    async (username: string, password: string) => {
      try {
        const response = await loginMutation.mutateAsync({
          data: {
            username,
            password,
          },
        });
        const newToken = response.data.access_token;
        saveToken(newToken);
      } catch (error) {
        console.error("Login failed:", error);
        throw error;
      }
    },
    [loginMutation, saveToken],
  );

  const logout = useCallback(() => {
    logoutMutation.mutate();
    setUser(null);
    removeToken();
    // ユーザーIDをクリア
    window.localStorage.removeItem("X-User-ID");
    // axiosのデフォルトヘッダーをクリア
    delete axios.defaults.headers.common["X-User-ID"];
  }, [logoutMutation, removeToken]);

  return (
    <AuthContext.Provider value={{ user, token, login, logout, loading }}>
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
