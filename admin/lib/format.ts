const intFmt = new Intl.NumberFormat("tr-TR");
const pctFmt = new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 0 });
const dayFmt = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", timeZone: "UTC" });

export const fmtInt = (n: number) => intFmt.format(Math.round(n));
export const fmtPct = (n: number) => pctFmt.format(n);
export const fmtDay = (iso: string) => dayFmt.format(new Date(iso + "T00:00:00Z"));

export function fmtDuration(sec: number) {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m ? `${m} dk ${s} sn` : `${s} sn`;
}

// Relative change; null when there is nothing to compare against.
export function change(cur: number, prev: number): number | null {
  if (!prev) return null;
  return (cur - prev) / prev;
}

export function fmtAgo(iso: string, now = Date.now()) {
  const min = Math.round((now - new Date(iso).getTime()) / 60000);
  if (min < 60) return `${min} dk önce`;
  const h = Math.round(min / 60);
  if (h < 48) return `${h} saat önce`;
  return `${Math.round(h / 24)} gün önce`;
}

// GA4's English channel and device names, in Turkish.
const LABELS: Record<string, string> = {
  "Organic Search": "Organik arama",
  Direct: "Doğrudan",
  "Organic Social": "Organik sosyal",
  Referral: "Başka siteler",
  "Paid Search": "Ücretli arama",
  "Paid Social": "Ücretli sosyal",
  Email: "E-posta",
  Display: "Görüntülü reklam",
  "Organic Video": "Organik video",
  Unassigned: "Atanmamış",
  "Cross-network": "Ağlar arası",
  mobile: "Mobil",
  desktop: "Masaüstü",
  tablet: "Tablet",
  smarttv: "Akıllı TV",
  "(direct)": "(doğrudan)",
  "(not set)": "(belirsiz)",
};
export const label = (s: string) => LABELS[s] ?? s;
