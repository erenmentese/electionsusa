import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, authDisabled, isValidSession } from "@/lib/auth";

export async function middleware(req: NextRequest) {
  if (authDisabled()) return NextResponse.next();
  if (await isValidSession(req.cookies.get(SESSION_COOKIE)?.value)) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!login|api/login|_next/|favicon.ico|robots.txt).*)"],
};
