import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token");
  const isLoginPage = request.nextUrl.pathname === "/login";
  const isSignupPage = request.nextUrl.pathname === "/signup";
  const isApiRoute =
    request.nextUrl.pathname.startsWith("/api/") ||
    request.nextUrl.pathname === "/api";

  if (isApiRoute) {
    return NextResponse.next();
  }

  // 1. 認証不要なページの処理
  if (isLoginPage || isSignupPage) {
    // ログインページで認証済みの場合はexecutionにリダイレクト
    if (isLoginPage && token) {
      return NextResponse.redirect(new URL("/execution", request.url));
    }
    return NextResponse.next();
  }

  // 2. その他のページは認証が必要
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
     * 除外: _next/static, _next/image, favicon, 静的ファイル（画像等）
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.png$|.*\\.svg$|.*\\.jpg$|.*\\.jpeg$|.*\\.gif$|.*\\.ico$).*)",
  ],
};
