import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { clearSessionCookie } from "@/lib/auth/cookies";

export function GET(request: NextRequest): NextResponse {
  const response = NextResponse.redirect(new URL("/login", request.url));
  clearSessionCookie(response);
  return response;
}
