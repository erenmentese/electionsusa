"""One row set per real poll before anything is averaged.

Wikipedia's tables sometimes list the same poll twice (sponsor and pollster swapped,
"Zogby" next to "Zogby Analytics", "Reuters/Ipsos" next to "Reuters" + "Ipsos"), and many
pollsters publish one poll for several populations (likely voters, registered voters,
all adults). Counted separately, each copy carries its own weight in the average.

A poll is identified by (race, fieldwork start, fieldwork end, the firm that ran it, the
other organisations named on it). Inside that group:

* one population is kept, in the order LV > RV > A > unknown (`POPULATION_ORDER`);
* a second row for the same population is a copy when every shared number is within
  `TOLERANCE` points; otherwise it is a different poll and both stay.

The partner set matters: "The Washington Post/Ipsos" and "Reuters/Ipsos" from the same days
are two polls, while "ABC News/Washington Post/Ipsos" and "Washington Post" + "ABC News/Ipsos"
are one.
"""
from __future__ import annotations

import pandas as pd

from . import pollsters

POPULATION_ORDER = {"LV": 0, "RV": 1, "A": 2}
TOLERANCE = 1.0

# Separate firms run by the same family, treated as one when matching copies only
# (pollster pages keep them apart): John Zogby's firm and Zogby Analytics.
FAMILY = {"johnzogbystrategies": "zogbyanalytics"}
# Outlets written with and without "News"
OUTLETS = {"yahoonews": "yahoo", "abcnews": "abc", "cbsnews": "cbs", "nbcnews": "nbc"}


def _firm_key(pollster: str, sponsor: str) -> str:
    k = pollsters.key(pollsters.firm(pollster, sponsor) or pollster)
    return FAMILY.get(k, k)


def _partners(pollster: str, sponsor: str, firm_key: str) -> frozenset[str]:
    out = set()
    for n in f"{pollster}/{sponsor}".split("/"):
        k = pollsters.key(n)
        if not k:
            continue
        k = pollsters.key(pollsters.ALIASES.get(k, n))
        if FAMILY.get(k, k) != firm_key:
            out.add(OUTLETS.get(k, k))
    return frozenset(out)


def poll_groups(polls: pd.DataFrame) -> pd.DataFrame:
    """One row per poll_id with its group key, population rank and numbers."""
    meta = polls.drop_duplicates("poll_id").set_index("poll_id")
    sponsor = meta["sponsor"].where(meta["sponsor"].map(lambda s: isinstance(s, str)), "")
    firm = [_firm_key(p, s) for p, s in zip(meta["pollster"], sponsor)]
    group = [(r, str(st), str(en), f, _partners(p, s, f))
             for r, st, en, f, p, s in zip(meta["race_id"], meta["start_date"], meta["end_date"], firm, meta["pollster"], sponsor)]
    vals = polls.pivot_table(index="poll_id", columns="candidate", values="pct", aggfunc="first")
    out = pd.DataFrame({"group": group, "pop_rank": meta["population"].fillna("").map(lambda p: POPULATION_ORDER.get(p, 3)),
                        "has_n": meta["sample_size"].notna(), "fetched": meta["fetched_at"].fillna("").astype(str)}, index=meta.index)
    return out.join(vals)


def _same(a: pd.Series, b: pd.Series) -> bool:
    shared = a.notna() & b.notna()
    return bool(shared.any()) and bool(((a[shared] - b[shared]).abs() <= TOLERANCE).all())


def plan(polls: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """poll_id to drop -> (reason, poll_id kept). Reason is "copy" or "population"."""
    if polls.empty:
        return {}
    g = poll_groups(polls)
    cands = [c for c in g.columns if c not in ("group", "pop_rank", "has_n", "fetched")]
    drop: dict[str, tuple[str, str]] = {}
    for _, rows in g.groupby("group", sort=False):
        if len(rows) < 2:
            continue
        rows = rows.sort_values(["pop_rank", "has_n", "fetched"], ascending=[True, False, False])
        kept: list[str] = []
        for pid, r in rows.iterrows():
            if not kept:
                kept.append(pid)
                continue
            top = rows.loc[kept[0]]
            twin = next((k for k in kept if rows.loc[k, "pop_rank"] == r["pop_rank"] and _same(rows.loc[k, cands], r[cands])), None)
            if twin:
                drop[pid] = ("copy", twin)
            elif r["pop_rank"] == 3 and _same(top[cands], r[cands]):
                drop[pid] = ("copy", kept[0])  # unknown population, same numbers: the same poll
            elif r["pop_rank"] > top["pop_rank"]:
                drop[pid] = ("population", kept[0])
            else:
                kept.append(pid)  # same population, different numbers: a different poll
    return drop


def collapse(polls: pd.DataFrame) -> pd.DataFrame:
    """polls without copies and secondary populations (see the module docstring)."""
    drop = plan(polls)
    return polls[~polls["poll_id"].isin(drop)].reset_index(drop=True) if drop else polls


def copies(polls: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """Only the exact copies: the same poll entered twice, which polls.csv should never hold."""
    return {k: v for k, v in plan(polls).items() if v[0] == "copy"}
