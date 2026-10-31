import "server-only";
import { BetaAnalyticsDataClient } from "@google-analytics/data";
import { getVercelOidcToken } from "@vercel/oidc";
import { ExternalAccountClient } from "google-auth-library";
import type { Dashboard, Range, Row, Totals } from "./types";
import { sampleDashboard } from "./sample";

// GA4_PROPERTY_ID: the numeric property id (GA4 > Admin > Property details).
// Auth, preferred: keyless Workload Identity Federation with Vercel OIDC (GCP_PROJECT_NUMBER,
// GCP_SERVICE_ACCOUNT_EMAIL, GCP_WORKLOAD_IDENTITY_POOL_ID, GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID).
// Fallback: GA4_CREDENTIALS, a service-account JSON key pasted as-is or base64-encoded.
function client(): BetaAnalyticsDataClient {
  const sa = process.env.GCP_SERVICE_ACCOUNT_EMAIL;
  if (sa) {
    const provider = `projects/${process.env.GCP_PROJECT_NUMBER}/locations/global/workloadIdentityPools/${process.env.GCP_WORKLOAD_IDENTITY_POOL_ID}/providers/${process.env.GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID}`;
    const authClient = ExternalAccountClient.fromJSON({
      type: "external_account",
      audience: `//iam.googleapis.com/${provider}`,
      subject_token_type: "urn:ietf:params:oauth:token-type:jwt",
      token_url: "https://sts.googleapis.com/v1/token",
      service_account_impersonation_url: `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${sa}:generateAccessToken`,
      subject_token_supplier: { getSubjectToken: () => getVercelOidcToken() },
      // The default cloud-platform scope is not accepted by the GA4 Data API.
      scopes: ["https://www.googleapis.com/auth/analytics.readonly"],
    });
    if (!authClient) throw new Error("Could not build the Workload Identity Federation client");
    return new BetaAnalyticsDataClient({ authClient });
  }
  const raw = process.env.GA4_CREDENTIALS!.trim();
  const parsed = JSON.parse(raw.startsWith("{") ? raw : Buffer.from(raw, "base64").toString("utf8"));
  return new BetaAnalyticsDataClient({ credentials: { client_email: parsed.client_email, private_key: parsed.private_key } });
}

export function gaConfigured(): boolean {
  return !!process.env.GA4_PROPERTY_ID && !!(process.env.GCP_SERVICE_ACCOUNT_EMAIL || process.env.GA4_CREDENTIALS);
}

const num = (v: string | null | undefined) => Number(v ?? 0) || 0;

export async function getDashboard(range: Range): Promise<Dashboard> {
  if (!gaConfigured()) return sampleDashboard(range);
  try {
    return await fetchDashboard(range);
  } catch (e) {
    console.error("GA4 request failed", e);
    const message = e instanceof Error ? e.message : String(e);
    return { ...sampleDashboard(range), error: message };
  }
}

async function fetchDashboard(range: Range): Promise<Dashboard> {
  const ga = client();
  const property = `properties/${process.env.GA4_PROPERTY_ID}`;
  // Each range ends today and includes it; the comparison range is the same length just before.
  const current = { startDate: `${range - 1}daysAgo`, endDate: "today", name: "current" };
  const previous = { startDate: `${range * 2 - 1}daysAgo`, endDate: `${range}daysAgo`, name: "previous" };

  const top = (dimension: string, metric: string, limit: number) =>
    ga.runReport({
      property,
      dateRanges: [current],
      dimensions: [{ name: dimension }],
      metrics: [{ name: metric }],
      orderBys: [{ metric: { metricName: metric }, desc: true }],
      limit,
    });

  const [[totals], [daily], [pages], [channels], [sources], [countries], [devices], realtime] = await Promise.all([
    ga.runReport({
      property,
      dateRanges: [current, previous],
      metrics: ["activeUsers", "newUsers", "sessions", "screenPageViews", "averageSessionDuration", "engagementRate"].map((name) => ({ name })),
    }),
    ga.runReport({
      property,
      dateRanges: [current],
      dimensions: [{ name: "date" }],
      metrics: [{ name: "activeUsers" }, { name: "screenPageViews" }],
      orderBys: [{ dimension: { dimensionName: "date" } }],
      limit: 400,
    }),
    ga.runReport({
      property,
      dateRanges: [current],
      dimensions: [{ name: "pagePath" }],
      metrics: [{ name: "screenPageViews" }, { name: "activeUsers" }],
      orderBys: [{ metric: { metricName: "screenPageViews" }, desc: true }],
      limit: 10,
    }),
    top("sessionDefaultChannelGroup", "sessions", 8),
    top("sessionSource", "sessions", 8),
    top("country", "activeUsers", 8),
    top("deviceCategory", "activeUsers", 5),
    ga.runRealtimeReport({ property, metrics: [{ name: "activeUsers" }] }).catch(() => null),
  ]);

  const totalsFor = (name: string): Totals => {
    const row = totals.rows?.find((r) => r.dimensionValues?.[0]?.value === name);
    const m = row?.metricValues ?? [];
    return {
      users: num(m[0]?.value),
      newUsers: num(m[1]?.value),
      sessions: num(m[2]?.value),
      views: num(m[3]?.value),
      avgSessionSec: num(m[4]?.value),
      engagementRate: num(m[5]?.value),
    };
  };

  // GA leaves out days with no data; fill them so the chart has one point per day.
  const byDate = new Map(
    (daily.rows ?? []).map((r) => {
      const d = r.dimensionValues![0].value!;
      return [`${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`, r.metricValues!];
    }),
  );
  // GA counts days in the property's time zone, which may be ahead of or behind UTC; end on
  // GA's latest day so the chart neither drops its newest day nor ends on a fake zero.
  const latest = [...byDate.keys()].sort().pop();
  const yesterdayUtc = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const end = new Date((latest && latest > yesterdayUtc ? latest : yesterdayUtc) + "T00:00:00Z").getTime();
  const days: Dashboard["daily"] = [];
  for (let i = range - 1; i >= 0; i--) {
    const date = new Date(end - i * 86400000).toISOString().slice(0, 10);
    const m = byDate.get(date);
    days.push({ date, users: num(m?.[0]?.value), views: num(m?.[1]?.value) });
  }

  const rows = (report: typeof channels): Row[] =>
    (report.rows ?? []).map((r) => ({ name: r.dimensionValues![0].value || "(bilinmiyor)", value: num(r.metricValues![0].value) }));

  const realtimeReport = realtime?.[0];
  return {
    source: "ga4",
    range,
    realtimeUsers: realtimeReport ? num(realtimeReport.rows?.[0]?.metricValues?.[0]?.value) : null,
    current: totalsFor("current"),
    previous: totalsFor("previous"),
    daily: days,
    pages: (pages.rows ?? []).map((r) => ({
      path: r.dimensionValues![0].value!,
      views: num(r.metricValues![0].value),
      users: num(r.metricValues![1].value),
    })),
    channels: rows(channels),
    sources: rows(sources),
    countries: rows(countries),
    devices: rows(devices),
  };
}
