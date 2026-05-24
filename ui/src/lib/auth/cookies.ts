import { NextResponse } from "next/server";

export const ACCESS_TOKEN_COOKIE = "access_token";

export function clearSessionCookie(response: NextResponse): void {
  response.cookies.set({
    name: ACCESS_TOKEN_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  response.headers.append(
    "Set-Cookie",
    `${ACCESS_TOKEN_COOKIE}=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax`,
  );
}
