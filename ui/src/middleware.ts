import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("token");
  const isLoginPage = request.nextUrl.pathname === "/login";
  const isApiRequest = request.nextUrl.pathname.startsWith("/api/");

  // APIリクエストはスキップ
  if (isApiRequest) {
    return NextResponse.next();
  }

  // ログインページにいる場合、トークンがあればホームにリダイレクト
  if (isLoginPage && token) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  // ログインページ以外でトークンがない場合、ログインページにリダイレクト
  if (!isLoginPage && !token && !isApiRequest) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

// 認証が必要なパスを指定
export const config = {
  matcher: [
    /*
     * 以下のパスに対してミドルウェアを適用:
     * - /login
     * - /calibration, /chip, /execution, /experiment, /fridge, /setting
     * - /api/* (APIリクエストをスキップするため)
     */
    "/login",
    "/calibration/:path*",
    "/chip/:path*",
    "/execution/:path*",
    "/experiment/:path*",
    "/fridge/:path*",
    "/setting/:path*",
    "/api/:path*",
  ],
};
