import type { Dashboard, Range, Totals } from "./types";

// Plausible made-up numbers for a young site, shown until GA4 credentials are set.
// Seeded so the page doesn't change on every refresh.
function rng(seed: number) {
  return () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
}

export function sampleDashboard(range: Range): Dashboard {
  const rand = rng(2028);
  const daily: Dashboard["daily"] = [];
  for (let i = range * 2 - 1; i >= 0; i--) {
    const date = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
    const growth = 1 + (range * 2 - i) / (range * 2);
    const weekday = new Date(date).getUTCDay();
    const weekend = weekday === 0 || weekday === 6 ? 0.75 : 1;
    const users = Math.round((40 + rand() * 30) * growth * weekend);
    daily.push({ date, users, views: Math.round(users * (1.8 + rand() * 0.6)) });
  }
  const prevDays = daily.slice(0, range);
  const curDays = daily.slice(range);
  const totals = (days: typeof daily): Totals => {
    const users = days.reduce((s, d) => s + d.users, 0);
    const views = days.reduce((s, d) => s + d.views, 0);
    return {
      users: Math.round(users * 0.82),
      newUsers: Math.round(users * 0.64),
      sessions: Math.round(users * 1.15),
      views,
      avgSessionSec: 74 + rand() * 30,
      engagementRate: 0.48 + rand() * 0.1,
    };
  };
  const cur = totals(curDays);
  const scale = (share: number) => Math.round(cur.views * share);
  return {
    source: "sample",
    range,
    realtimeUsers: 3,
    current: cur,
    previous: totals(prevDays),
    daily: curDays,
    pages: [
      ["/", 0.31],
      ["/pres-2028-vance-newsom/", 0.14],
      ["/approval-trump-2/", 0.11],
      ["/dem-primary-2028/", 0.09],
      ["/gop-primary-2028/", 0.07],
      ["/countdown/", 0.06],
      ["/markets/", 0.05],
      ["/pollsters/", 0.04],
      ["/generic-ballot-2026/", 0.03],
      ["/methodology/", 0.02],
    ].map(([path, share]) => ({ path: path as string, views: scale(share as number), users: Math.round(scale(share as number) * 0.6) })),
    channels: [
      { name: "Organic Search", value: Math.round(cur.sessions * 0.46) },
      { name: "Direct", value: Math.round(cur.sessions * 0.27) },
      { name: "Organic Social", value: Math.round(cur.sessions * 0.17) },
      { name: "Referral", value: Math.round(cur.sessions * 0.1) },
    ],
    sources: [
      { name: "google", value: Math.round(cur.sessions * 0.41) },
      { name: "(direct)", value: Math.round(cur.sessions * 0.27) },
      { name: "t.co", value: Math.round(cur.sessions * 0.12) },
      { name: "bing", value: Math.round(cur.sessions * 0.05) },
      { name: "reddit.com", value: Math.round(cur.sessions * 0.05) },
      { name: "duckduckgo", value: Math.round(cur.sessions * 0.03) },
    ],
    countries: [
      { name: "United States", value: Math.round(cur.users * 0.78) },
      { name: "Canada", value: Math.round(cur.users * 0.06) },
      { name: "United Kingdom", value: Math.round(cur.users * 0.04) },
      { name: "Türkiye", value: Math.round(cur.users * 0.03) },
      { name: "Germany", value: Math.round(cur.users * 0.02) },
      { name: "India", value: Math.round(cur.users * 0.02) },
    ],
    devices: [
      { name: "mobile", value: Math.round(cur.users * 0.61) },
      { name: "desktop", value: Math.round(cur.users * 0.35) },
      { name: "tablet", value: Math.round(cur.users * 0.04) },
    ],
  };
}
