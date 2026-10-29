// Single-password login. The session cookie holds an HMAC of a fixed label keyed by
// ADMIN_PASSWORD, so changing the password logs every browser out. Web Crypto only,
// so the same code runs in middleware (edge) and route handlers (node).

export const SESSION_COOKIE = "eusa_admin";
export const SESSION_MAX_AGE = 60 * 60 * 24 * 30; // 30 days

export function adminPassword(): string | undefined {
  const p = process.env.ADMIN_PASSWORD;
  return p && p.length > 0 ? p : undefined;
}

// Without a password the panel is open in local development only; in production it stays locked.
export function authDisabled(): boolean {
  return !adminPassword() && process.env.NODE_ENV !== "production";
}

export async function sessionToken(password: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(password), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode("electionsusa-admin-v1")));
  return Array.from(sig, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function isValidSession(cookie: string | undefined): Promise<boolean> {
  const password = adminPassword();
  if (!password || !cookie) return false;
  return safeEqual(cookie, await sessionToken(password));
}
