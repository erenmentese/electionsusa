"""Network step: fetch fresh polls and market prices, merge into data/*.csv.

Designed for GitHub Actions (open network). Safe to run anywhere: on failure the
existing CSVs are left untouched. Seed rows are superseded by fetched rows with
the same (race, pollster, end_date, population).

    python -m pipeline.run_pipeline            # fetch everything
    python -m pipeline.run_pipeline --no-markets
"""
from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from . import config, fetch_markets, fetch_wikipedia
from .schema import MARKET_COLUMNS, POLL_COLUMNS, validate_polls

log = logging.getLogger("pipeline")


def merge_polls(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    if fresh.empty:
        return existing
    fresh = validate_polls(fresh)
    existing = validate_polls(existing) if not existing.empty else existing
    key = ["race_id", "pollster", "end_date", "population", "candidate"]
    if existing.empty:
        return fresh
    # fetched rows win over seed rows; keep manual rows always
    manual = existing[existing["source_type"] == "manual"]
    auto = existing[existing["source_type"] != "manual"]
    merged = pd.concat([auto, fresh]).drop_duplicates(subset=key, keep="last")
    merged = pd.concat([merged, manual]).drop_duplicates(subset=key, keep="last")
    return merged.sort_values(["race_id", "end_date"], ascending=[True, False]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-markets", action="store_true")
    ap.add_argument("--no-polls", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    polls_path = config.DATA_DIR / "polls.csv"
    markets_path = config.DATA_DIR / "markets.csv"
    polls = pd.read_csv(polls_path) if polls_path.exists() else pd.DataFrame(columns=POLL_COLUMNS)
    markets = pd.read_csv(markets_path) if markets_path.exists() else pd.DataFrame(columns=MARKET_COLUMNS)

    if not args.no_polls:
        fresh = fetch_wikipedia.fetch_all()
        before = len(polls)
        polls = merge_polls(polls, fresh)
        log.info("polls: %d -> %d rows (%d fetched)", before, len(polls), len(fresh))
        polls.to_csv(polls_path, index=False)
    if not args.no_markets:
        snap = fetch_markets.fetch_all()
        if not snap.empty:
            markets = pd.concat([markets, snap]).drop_duplicates(
                subset=["snapshot_date", "market_id", "platform", "outcome"], keep="last")
            markets.to_csv(markets_path, index=False)
            log.info("markets: +%d rows", len(snap))
        else:
            log.warning("markets: nothing fetched; keeping existing file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
