"""Run the X bot.

    python -m pipeline.run_bot                 # dry run: print posts, write PNG cards to out/bot/
    python -m pipeline.run_bot --live          # publish (needs X_* credentials)
    python -m pipeline.run_bot --bootstrap     # mark every existing poll as already posted
    python -m pipeline.run_bot --preview-all   # render one example of every post type

On the first live run with no data/bot_state.json, the bot bootstraps
automatically so a new account does not get a backlog of old polls.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone

import pandas as pd

from . import config, scorecard, social_compose as sc
from .social_cards import render
from .social_text import weighted_length
from .xclient import XClient, XError, credentials_present

log = logging.getLogger("bot")
OUT = config.ROOT / "out" / "bot"


def write_preview(posts, tag: str = "") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(posts, 1):
        stem = f"{tag}{i:02d}-{p.kind}"
        (OUT / f"{stem}.txt").write_text(p.text + "\n")
        if p.card:
            (OUT / f"{stem}.png").write_bytes(render(p.card))
        print(f"--- [{p.kind}] {p.key}  ({weighted_length(p.text)}/280)\n{p.text}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--preview-all", action="store_true")
    ap.add_argument("--today", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    now = datetime.now(timezone.utc)
    today = args.today or now.date()
    polls = pd.read_csv(config.DATA_DIR / "polls.csv")
    _, ratings = scorecard.load_538()

    if args.preview_all:
        polls_v = sc.validate_polls(polls)
        latest = polls_v.sort_values("end_date").groupby("race_id").tail(1)["poll_id"].unique()
        posts = [p for pid in latest if (p := sc.poll_post(pid, polls_v, ratings, today))]
        rp = sc.roundup_post(polls_v, ratings, today)
        posts += [rp] if rp else []
        posts += sc.milestone_posts(today)
        if not any(p.key.startswith("milestone:2028") for p in posts):
            from datetime import timedelta
            posts += sc.milestone_posts(config.ELECTION_DAY_2028 - timedelta(days=700))[:1]
        write_preview(posts, "example-")
        print(f"wrote {len(posts)} examples to {OUT}")
        return 0

    state = sc.load_state()
    first_run = state is None
    state = state or sc.empty_state()
    if args.bootstrap or (first_run and args.live):
        n = sc.bootstrap(polls, state, now)
        sc.save_state(state)
        log.info("bootstrap: marked %d existing polls as posted%s", n, " (first live run)" if first_run and not args.bootstrap else "")
        if args.bootstrap:
            return 0

    posts = sc.plan(polls, ratings, state, today, now)
    if not posts:
        log.info("nothing to post")
        if args.live:
            sc.save_state(state)
        return 0

    if not args.live:
        write_preview(posts)
        log.info("dry run: %d post(s) planned, cards in %s (nothing published)", len(posts), OUT)
        return 0

    if not credentials_present():
        log.error("--live needs X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET")
        return 2
    client = XClient()
    status = 0
    for p in posts:
        try:
            png = render(p.card) if p.card else None
            post_id = client.post_with_card(p.text, png, p.alt)
            state["posted"][p.key] = now.isoformat()
            state["log"].append({"ts": now.isoformat(), "key": p.key, "id": post_id, "live": True})
            log.info("posted %s -> https://x.com/i/status/%s", p.key, post_id)
        except XError as e:
            log.error("failed %s: %s", p.key, e)
            status = 1
            if "rate limited" in str(e):
                break
        finally:
            sc.save_state(state)
    return status


if __name__ == "__main__":
    sys.exit(main())
