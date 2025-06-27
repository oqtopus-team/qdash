import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("token");
  const isLoginPage = request.nextUrl.pathname === "/login";
  const isSignupPage = request.nextUrl.pathname === "/signup";
  const isApiRequest = request.nextUrl.pathname.startsWith("/api/");

  // 1. APIリクエストはスキップ
  if (isApiRequest) {
    return NextResponse.next();
  }

  // 2. 認証不要なページの処理
  if (isLoginPage || isSignupPage) {
    // ログインページで認証済みの場合はexecutionにリダイレクト
    if (isLoginPage && token) {
      return NextResponse.redirect(new URL("/execution", request.url));
    }
    return NextResponse.next();
  }

  // 3. その他のページは認証が必要
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

// 認証が必要なパスを指定
export const config = {
  matcher: [
    /*
     * 以下のパスに対してミドルウェアを適用:
     * - すべてのパス（/:path*）
     * - ルートパス（/）
     * - /api/* (APIリクエストをスキップするため)
     */
    "/((?!_next/static|favicon.ico).*)",
  ],
};
