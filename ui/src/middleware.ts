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

  // 1. Handle pages that don't require authentication
  if (isLoginPage || isSignupPage) {
    // Redirect to execution if already authenticated on login page
    if (isLoginPage && token) {
      return NextResponse.redirect(new URL("/execution", request.url));
    }
    return NextResponse.next();
  }

  // 2. Other pages require authentication
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

// Specify paths that require authentication
export const config = {
  matcher: [
    /*
     * Apply middleware to the following paths:
     * - All paths (/:path*)
     * - Root path (/)
     * Exclude: _next/static, _next/image, favicon, static files (images, etc.)
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.png$|.*\\.svg$|.*\\.jpg$|.*\\.jpeg$|.*\\.gif$|.*\\.ico$).*)",
  ],
};
