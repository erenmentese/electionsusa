import Link from "next/link";
import Bars, { Split } from "@/components/Bars";
import LineChart from "@/components/LineChart";
import { authDisabled } from "@/lib/auth";
import { change, fmtAgo, fmtDuration, fmtInt, fmtPct } from "@/lib/format";
import { getDashboard } from "@/lib/ga";
import { getHealth } from "@/lib/health";
import { RANGES, type Range, type Totals } from "@/lib/types";

export const dynamic = "force-dynamic";

const KPIS: { key: keyof Totals; label: string; format: (n: number) => string }[] = [
  { key: "users", label: "Ziyaretçi", format: fmtInt },
  { key: "newUsers", label: "Yeni ziyaretçi", format: fmtInt },
  { key: "sessions", label: "Oturum", format: fmtInt },
  { key: "views", label: "Sayfa görüntüleme", format: fmtInt },
  { key: "avgSessionSec", label: "Ort. oturum süresi", format: fmtDuration },
  { key: "engagementRate", label: "Etkileşim oranı", format: fmtPct },
];

function Delta({ cur, prev }: { cur: number; prev: number }) {
  const c = change(cur, prev);
  if (c === null) return <span className="delta muted">karşılaştırma yok</span>;
  const up = c >= 0;
  return (
    <span className={`delta ${up ? "up" : "down"}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span> {fmtPct(Math.abs(c))}
      <span className="sr-only">{up ? " artış" : " düşüş"}</span>
    </span>
  );
}

export default async function Page({ searchParams }: { searchParams: Promise<{ r?: string }> }) {
  const { r } = await searchParams;
  const range = (RANGES.find((v) => String(v) === r) ?? 28) as Range;
  const [d, health] = await Promise.all([getDashboard(range), getHealth()]);

  const run = health.run;
  const ageH = run ? (Date.now() - new Date(run.at).getTime()) / 3600000 : null;
  const status = !run || ageH === null ? null : !run.ok || ageH >= 24 ? "critical" : ageH >= 8 ? "warning" : "good";
  const statusText = { good: "Normal", warning: "Gecikmeli", critical: run && !run.ok ? "Son çalışma başarısız" : "Durmuş olabilir" };
  const statusIcon = { good: "✓", warning: "!", critical: "✕" };

  return (
    <>
      <header className="top">
        <div className="wrap top-inner">
          <p className="brand">Elections<em>USA</em> <span className="muted">Yönetim</span></p>
          <nav className="ranges" aria-label="Dönem">
            {RANGES.map((v) => (
              <Link key={v} href={`/?r=${v}`} aria-current={v === range ? "page" : undefined}>Son {v} gün</Link>
            ))}
          </nav>
          {!authDisabled() && (
            <form method="post" action="/api/logout"><button className="link">Çıkış</button></form>
          )}
        </div>
      </header>

      <main className="wrap">
        {d.source === "sample" && (
          <p className="notice" role="status">
            {d.error
              ? <>GA4'ten veri alınamadı, örnek veri gösteriliyor. Hata: <code>{d.error}</code></>
              : <>Örnek veri gösteriliyor. GA4 bağlantısı kurulunca gerçek rakamlar gelecek.</>}
          </p>
        )}

        <p className="muted small kpi-note">Son {range} gün · değişimler ondan önceki {range} güne göre</p>
        <section className="kpis" aria-label="Özet">
          <div className="kpi hero">
            <p className="kpi-label"><span className="live" aria-hidden="true" />Şu an sitede</p>
            <p className="kpi-value">{d.realtimeUsers === null ? "–" : fmtInt(d.realtimeUsers)}</p>
            <p className="delta muted">son 30 dakikada aktif ziyaretçi</p>
          </div>
          {KPIS.map((k) => (
            <div className="kpi" key={k.key}>
              <p className="kpi-label">{k.label}</p>
              <p className="kpi-value">{k.format(d.current[k.key])}</p>
              <Delta cur={d.current[k.key]} prev={d.previous[k.key]} />
            </div>
          ))}
        </section>

        <section className="grid2">
          <div className="card">
            <h2>Günlük ziyaretçi</h2>
            <LineChart label="Ziyaretçi" points={d.daily.map((p) => ({ date: p.date, value: p.users }))} />
          </div>
          <div className="card">
            <h2>Günlük sayfa görüntüleme</h2>
            <LineChart label="Görüntüleme" points={d.daily.map((p) => ({ date: p.date, value: p.views }))} />
          </div>
        </section>

        <section className="grid2">
          <div className="card">
            <h2>En çok okunan sayfalar</h2>
            {d.pages.length ? (
              <table className="pages">
                <thead><tr><th>Sayfa</th><th className="num">Görüntüleme</th><th className="num">Ziyaretçi</th></tr></thead>
                <tbody>
                  {d.pages.map((p) => (
                    <tr key={p.path}>
                      <td><a href={`https://electionsusa.org${p.path}`} target="_blank" rel="noopener">{p.path}</a></td>
                      <td className="num">{fmtInt(p.views)}</td>
                      <td className="num">{fmtInt(p.users)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="muted small">Henüz veri yok</p>}
          </div>
          <div className="card">
            <h2>Ziyaretçiler nereden geliyor</h2>
            <Bars rows={d.channels} unit="oturum" />
            <h3>Kaynaklar</h3>
            <Bars rows={d.sources} unit="oturum" />
          </div>
        </section>

        <section className="grid3">
          <div className="card">
            <h2>Ülkeler</h2>
            <Bars rows={d.countries} unit="ziyaretçi" />
          </div>
          <div className="card">
            <h2>Cihazlar</h2>
            <Split rows={d.devices} />
          </div>
          <div className="card">
            <h2>Site sağlığı</h2>
            {status && run ? (
              <p className={`status ${status}`}>
                <span className="status-icon" aria-hidden="true">{statusIcon[status]}</span>
                <span><strong>Veri güncellemesi: {statusText[status]}</strong><br />
                  <span className="muted small">
                    Son çalışma <a href={run.url} target="_blank" rel="noopener">{fmtAgo(run.at)}</a> (her 6 saatte bir çalışır).
                    {health.lastNewPolls && <> Son yeni anket {fmtAgo(health.lastNewPolls)} eklendi.</>}
                  </span></span>
              </p>
            ) : <p className="muted small">GitHub'dan güncelleme durumu alınamadı.</p>}
            <h3>Reklam geliri</h3>
            <p className="muted small">AdSense onaylanıp bağlandığında gelir ve sayfa başına kazanç burada görünecek.</p>
          </div>
        </section>
      </main>
    </>
  );
}
