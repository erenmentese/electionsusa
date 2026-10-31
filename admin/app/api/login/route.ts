import { NextResponse } from "next/server";
import { SESSION_COOKIE, SESSION_MAX_AGE, adminPassword, safeEqual, sessionToken } from "@/lib/auth";

export async function POST(req: Request) {
  const form = await req.formData();
  const given = String(form.get("password") ?? "");
  const password = adminPassword();
  const ok = !!password && safeEqual(await sessionToken(given), await sessionToken(password));

  if (!ok) {
    await new Promise((r) => setTimeout(r, 800)); // slow down guessing
    return NextResponse.redirect(new URL("/login?e=1", req.url), 303);
  }
  const res = NextResponse.redirect(new URL("/", req.url), 303);
  res.cookies.set(SESSION_COOKIE, await sessionToken(password), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });
  return res;
}
