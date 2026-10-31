export const RANGES = [7, 28, 90] as const;
export type Range = (typeof RANGES)[number];

export type Totals = {
  users: number;
  newUsers: number;
  sessions: number;
  views: number;
  avgSessionSec: number;
  engagementRate: number; // 0-1
};

export type Row = { name: string; value: number };

export type Dashboard = {
  source: "ga4" | "sample";
  range: Range;
  realtimeUsers: number | null;
  current: Totals;
  previous: Totals;
  daily: { date: string; users: number; views: number }[]; // date = YYYY-MM-DD
  pages: { path: string; views: number; users: number }[];
  channels: Row[]; // sessions
  sources: Row[]; // sessions
  countries: Row[]; // users
  devices: Row[]; // users
  error?: string;
};

export type Health = {
  run: { at: string; ok: boolean; url: string } | null; // last completed data-workflow run
  lastNewPolls: string | null; // ISO time data/polls.csv last changed
};
