"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  useAuthReadUsersMe,
  useAuthLogin,
  useAuthLogout,
} from "@/client/auth/auth";
import type { User } from "../../schemas";

interface AuthContextType {
  user: User | null;
  username: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // 認証情報の保存
  const saveAuth = useCallback((username: string) => {
    // トークンとしてユーザー名を保存（実際のJWTトークンと同様の扱い）
    document.cookie = `token=${encodeURIComponent(username)}; path=/; max-age=${
      7 * 24 * 60 * 60
    }; SameSite=Lax`;
    setUsername(username);
  }, []);

  // 認証情報の削除
  const removeAuth = useCallback(() => {
    document.cookie =
      "token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
    setUsername(null);
  }, []);

  // ログイン処理
  const loginMutation = useAuthLogin();

  // ログアウト処理
  const logoutMutation = useAuthLogout();

  // ユーザー情報の取得
  const { data: userData, error: userError } = useAuthReadUsersMe({
    query: {
      enabled: !!username,
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
      .find((row) => row.startsWith("token="))
      ?.split("=")[1];

    if (token) {
      try {
        const username = decodeURIComponent(token);
        setUsername(username);
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
        // 認証情報を保存
        saveAuth(response.data.username);
        // ユーザー情報が取得されるまで待つ
        await new Promise((resolve) => {
          const unsubscribe = () => {
            if (userData?.data) {
              clearInterval(interval);
              resolve(undefined);
            }
          };
          const interval = setInterval(() => {
            unsubscribe();
          }, 100);
          // 最大3秒待つ
          setTimeout(() => {
            clearInterval(interval);
            console.debug("User info fetch timeout, proceeding anyway");
            resolve(undefined);
          }, 3000);
        });
        // ログイン成功後にリダイレクト
        router.replace("/execution");
      } catch (error) {
        console.error("Login failed:", error);
        throw error;
      } finally {
        setLoading(false); // ローディング終了
      }
    },
    [loginMutation, saveAuth, router, userData]
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
