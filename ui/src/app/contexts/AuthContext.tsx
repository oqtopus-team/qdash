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

import type { User } from "../../schemas";

import {
  useGetCurrentUser,
  useLogin,
  useLogout,
} from "@/client/auth/auth";

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

  // 認証情報の保存
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

  // 認証情報の削除
  const removeAuth = useCallback(() => {
    // Remove access token and username cookies
    document.cookie =
      "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    document.cookie =
      "username=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    setAccessToken(null);
    setUsername(null);
  }, []);

  // ログイン処理
  const loginMutation = useLogin();

  // ログアウト処理
  const logoutMutation = useLogout();

  // ユーザー情報の取得
  const { data: userData, error: userError } = useGetCurrentUser({
    query: {
      enabled: !!accessToken,
      retry: false,
    },
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
      removeAuth();
      setUser(null);
    }
  }, [userError, removeAuth]);

  // 初期化処理
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
        setLoading(true); // ローディング開始
        const response = await loginMutation.mutateAsync({
          data: {
            username,
            password,
          },
        });

        // 認証情報を保存 (access_token と username)
        saveAuth(response.data.access_token, response.data.username);

        // 即座にリダイレクト
        router.replace("/execution");
      } catch (error) {
        console.error("Login failed:", error);
        // 認証情報をクリア
        removeAuth();
        setUser(null);
        throw error;
      } finally {
        setLoading(false); // ローディング終了
      }
    },
    [loginMutation, saveAuth, router, removeAuth],
  );

  const logout = useCallback(async () => {
    try {
      // まずログアウトAPIを呼び出し
      await logoutMutation.mutateAsync();
      // キャッシュをクリア
      await Promise.all([loginMutation.reset(), logoutMutation.reset()]);
      // 状態をクリア
      setUser(null);
      // 認証情報を削除（これによりmiddlewareが自動的にリダイレクトを行う）
      removeAuth();
      // 明示的にログインページに遷移
      window.location.href = "/login";
    } catch (error) {
      console.error("Logout failed:", error);
      // エラー時も同様の処理
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
