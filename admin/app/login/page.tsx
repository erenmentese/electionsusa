import { adminPassword } from "@/lib/auth";

export default async function Login({ searchParams }: { searchParams: Promise<{ e?: string }> }) {
  const { e } = await searchParams;
  const configured = !!adminPassword();
  return (
    <main className="login">
      <p className="brand">Elections<em>USA</em></p>
      <h1>Yönetim paneli</h1>
      {configured ? (
        <form method="post" action="/api/login">
          <label htmlFor="password">Şifre</label>
          <input id="password" name="password" type="password" autoComplete="current-password" required autoFocus />
          {e && <p className="error" role="alert">Şifre yanlış.</p>}
          <button type="submit">Giriş yap</button>
        </form>
      ) : (
        <p className="error" role="alert">Panel kilitli: Vercel ortam değişkenlerinde <code>ADMIN_PASSWORD</code> ayarlanmamış.</p>
      )}
    </main>
  );
}
