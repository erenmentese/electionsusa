import "server-only";
import type { Health } from "./types";

const REPO = "https://api.github.com/repos/erenmentese/electionsusa";

// Public repo, so no token; cached so the panel stays far below GitHub's anonymous rate limit.
async function github(path: string) {
  const res = await fetch(`${REPO}${path}`, { headers: { Accept: "application/vnd.github+json" }, next: { revalidate: 600 } });
  if (!res.ok) throw new Error(`GitHub ${res.status}`);
  return res.json();
}

// The "Update data and post" workflow runs every 6 hours (and on each push). Its last completed
// run tells whether the data pipeline is alive; data/polls.csv only changes when new polls appear.
export async function getHealth(): Promise<Health> {
  const [runs, commits] = await Promise.allSettled([
    github("/actions/workflows/update-and-deploy.yml/runs?status=completed&per_page=1"),
    github("/commits?path=data/polls.csv&per_page=1"),
  ]);
  const run = runs.status === "fulfilled" ? runs.value.workflow_runs?.[0] : undefined;
  const commit = commits.status === "fulfilled" ? commits.value?.[0] : undefined;
  return {
    run: run ? { at: run.updated_at, ok: run.conclusion === "success", url: run.html_url } : null,
    lastNewPolls: commit?.commit?.committer?.date ?? null,
  };
}
