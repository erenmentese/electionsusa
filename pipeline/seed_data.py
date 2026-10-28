"""Seed dataset: a small set of real, publicly reported polls and market prices.

Every row carries its source URL. Rows whose fieldwork dates could only be
inferred from press coverage say so in `notes`. The live pipeline
(run_pipeline.py) appends/replaces these with rows parsed from primary sources;
seed rows are kept only where no fetched row exists for the same poll.

Run:  python -m pipeline.seed_data   (rewrites data/polls.csv + data/markets.csv seed rows)
"""
from __future__ import annotations

import pandas as pd

from . import config
from .schema import MARKET_COLUMNS, POLL_COLUMNS, make_poll_id, now_iso, validate_polls

FETCHED = "2026-10-25T00:00:00Z"

# (race_id, pollster, sponsor, start, end, n, population, {candidate: pct}, url, notes)
SEED_POLLS = [
    # --- Trump approval -------------------------------------------------
    ("approval-trump-2", "Reuters/Ipsos", "", "2026-10-16", "2026-10-19", 1679, "A",
     {"Approve": 31},
     "https://www.thestar.com.my/news/world/2026/10/20/exclusive-trump-approval-falls-to-record-low-of-31-as-midterms-near-reutersipsos-poll-finds",
     "Four-day online poll closing Oct 19; overall disapprove figure not in coverage."),
    ("approval-trump-2", "Fox News", "", "2026-10-09", "2026-10-12", 1202, "RV",
     {"Approve": 36, "Disapprove": 64},
     "https://politicalwire.com/2026/10/14/trump-approval-at-record-low/",
     "Dates and sample size via secondary report of The Hill."),
    ("approval-trump-2", "ABC News/Washington Post/Ipsos", "", "2026-10-09", "2026-10-13", None, "A",
     {"Approve": 33, "Disapprove": 66},
     "https://easternherald.com/2026/10/18/trump-approval-record-low-abc-ipsos-poll/", ""),
    ("approval-trump-2", "The Economist/YouGov", "", "2026-10-10", "2026-10-13", None, "A",
     {"Approve": 34, "Disapprove": 61},
     "https://politicalwire.com/2026/10/14/trump-approval-at-34/",
     "Fieldwork dates approximate (reported Oct 14, 2026)."),
    ("approval-trump-2", "Pew Research Center", "", "2026-09-28", "2026-10-04", None, "A",
     {"Approve": 30},
     "https://www.pewresearch.org/chart/trumps-approval-rating-drops-to-30-on-par-with-his-rating-prior-to-leaving-office-in-january-2021/",
     "Disapprove figure not captured."),
    # --- 2026 generic ballot --------------------------------------------
    ("generic-ballot-2026", "Reuters/Ipsos", "", "2026-10-16", "2026-10-19", 1279, "RV",
     {"Democrats": 47, "Republicans": 35},
     "https://aljazeera.com/news/2026/10/19/trump-approval-hits-record-low-31-percent-polls-show-republican-struggles", ""),
    ("generic-ballot-2026", "Pew Research Center", "", "2026-09-28", "2026-10-04", None, "RV",
     {"Democrats": 44, "Republicans": 36},
     "https://politicalwire.com/2026/10/10/democrats-solidly-ahead-on-generic-ballot/",
     "Fieldwork dates assumed identical to Pew's approval release."),
    ("generic-ballot-2026", "Rasmussen Reports", "", "2026-01-26", "2026-01-29", None, "LV",
     {"Democrats": 47, "Republicans": 41},
     "https://www.rasmussenreports.com/public_content/politics/mood_of_america/generic_congressional_ballot",
     "January 2026 survey; exact dates approximate."),
    # --- 2028 general: Vance vs Newsom ------------------------------------
    ("pres-2028-vance-newsom", "Zogby Analytics", "", "2026-07-01", "2026-07-04", 1003, "LV",
     {"JD Vance": 45.1, "Gavin Newsom": 38.1},
     "https://gazette.com/?p=1021755", ""),
    ("pres-2028-vance-newsom", "Emerson College", "", "2025-10-13", "2025-10-14", 1000, "RV",
     {"JD Vance": 46, "Gavin Newsom": 45},
     "https://www.270towin.com/2028-presidential-election-polls/national", ""),
    ("pres-2028-vance-newsom", "Emerson College", "", "2025-08-25", "2025-08-26", 1000, "RV",
     {"JD Vance": 44.4, "Gavin Newsom": 43.5},
     "https://newsweek.com/gavin-newsom-gains-ground-jd-vance-2028-presidential-race-poll-10895389", ""),
    # --- 2028 general: Vance vs Ocasio-Cortez ------------------------------
    ("pres-2028-vance-ocasio-cortez", "Zogby Analytics", "", "2026-07-01", "2026-07-04", 1003, "LV",
     {"JD Vance": 45, "Alexandria Ocasio-Cortez": 37.6},
     "https://gazette.com/?p=1021755", ""),
    # --- 2028 Democratic primary -------------------------------------------
    ("dem-primary-2028", "Emerson College", "", "2026-07-19", "2026-07-20", 1110, "LV",
     {"Pete Buttigieg": 19, "Gavin Newsom": 17},
     "https://www.lgbtqnation.com/2026/07/pete-buttigieg-leads-democratic-primary-in-latest-poll/",
     "Only top two candidates captured from coverage; n is full-sample size."),
    ("dem-primary-2028", "Emerson College", "", "2026-05-24", "2026-05-25", None, "LV",
     {"Pete Buttigieg": 18, "Gavin Newsom": 16},
     "https://www.dailysignal.com/2026/05/28/democrat-presidential-candidates-poll/",
     "Only top two candidates captured from coverage."),
    ("dem-primary-2028", "AtlasIntel", "", "2026-05-04", "2026-05-07", None, "",
     {"Alexandria Ocasio-Cortez": 26, "Pete Buttigieg": 22.4, "Gavin Newsom": 21.2, "Kamala Harris": 12.9},
     "https://www.newsweek.com/new-poll-shows-how-top-2028-potential-democratic-candidates-have-shifted-12126335",
     "Fieldwork dates assumed to match AtlasIntel's May 4-7 GOP release."),
    ("dem-primary-2028", "The Economist/YouGov", "", "2026-04-10", "2026-04-13", None, "A",
     {"Kamala Harris": 29, "Pete Buttigieg": 9, "Gavin Newsom": 8, "Alexandria Ocasio-Cortez": 7},
     "https://www.newsweek.com/new-poll-shows-how-top-2028-potential-democratic-candidates-have-shifted-12126335",
     "April 2026 survey; exact dates approximate."),
    ("dem-primary-2028", "Yahoo News/YouGov", "", "2025-08-29", "2025-09-02", 1690, "A",
     {"Gavin Newsom": 21, "Kamala Harris": 19, "Alexandria Ocasio-Cortez": 12, "Pete Buttigieg": 10},
     "https://www.yahoo.com/news/articles/newsom-leads-2028-democratic-field-143521958.html",
     "Among registered Democratic and Democratic-leaning voters."),
    ("dem-primary-2028", "Emerson College", "", "2025-08-25", "2025-08-26", 1000, "RV",
     {"Gavin Newsom": 25, "Pete Buttigieg": 16, "Kamala Harris": 11},
     "https://www.yahoo.com/news/articles/newsom-support-surges-among-democrats-100000089.html", ""),
    # --- 2028 Republican primary -------------------------------------------
    ("gop-primary-2028", "Emerson College", "", "2026-05-24", "2026-05-25", None, "LV",
     {"JD Vance": 36, "Marco Rubio": 35, "Ron DeSantis": 5, "Nikki Haley": 5},
     "https://www.dailysignal.com/2026/05/28/vance-rubio-dead-heat-2028/", ""),
    ("gop-primary-2028", "AtlasIntel", "", "2026-05-04", "2026-05-07", None, "",
     {"Marco Rubio": 45.4, "JD Vance": 29.6, "Ron DeSantis": 11.2},
     "https://www.mediaite.com/media/news/shock-poll-marco-rubio-beats-jd-vance-by-double-digits-in-2028-primary-showdown/", ""),
    ("gop-primary-2028", "Big Data Poll", "", "2026-06-10", "2026-06-15", None, "",
     {"JD Vance": 35.4, "Marco Rubio": 16.5, "Ron DeSantis": 7.1, "Robert F. Kennedy Jr.": 6.5},
     "https://www.newsweek.com/new-poll-shows-jd-vance-ahead-of-potential-2028-candidates-by-double-digits-12152822",
     "Fieldwork dates approximate (reported mid-2026)."),
    ("gop-primary-2028", "Emerson College", "", "2026-02-10", "2026-02-12", None, "LV",
     {"JD Vance": 52, "Marco Rubio": 20},
     "https://www.dailysignal.com/2026/05/28/vance-rubio-dead-heat-2028/",
     "February 2026 survey cited as baseline; exact dates approximate."),
]

# (snapshot_date, market_id, platform, outcome, price, url, notes)
SEED_MARKETS = [
    ("2026-05-07", "pres-2028-winner", "polymarket", "JD Vance", 19.6,
     "https://www.coloradopolitics.com/2026/05/07/rubio-jumps-vance-as-most-likely-to-win-2028-presidential-race-on-kalshi/", "Press snapshot."),
    ("2026-05-07", "pres-2028-winner", "polymarket", "Gavin Newsom", 16.7,
     "https://www.coloradopolitics.com/2026/05/07/rubio-jumps-vance-as-most-likely-to-win-2028-presidential-race-on-kalshi/", "Press snapshot."),
    ("2026-05-07", "pres-2028-winner", "polymarket", "Marco Rubio", 15.0,
     "https://www.coloradopolitics.com/2026/05/07/rubio-jumps-vance-as-most-likely-to-win-2028-presidential-race-on-kalshi/", "Press snapshot."),
    ("2026-03-18", "pres-2028-winner", "polymarket", "JD Vance", 18.0,
     "https://casinobeats.com/2026/03/18/gavin-newsom-jd-vance-see-chances-leading-parties-2028-sharply-decline/", "Press snapshot."),
    ("2026-03-18", "pres-2028-winner", "polymarket", "Gavin Newsom", 17.0,
     "https://casinobeats.com/2026/03/18/gavin-newsom-jd-vance-see-chances-leading-parties-2028-sharply-decline/", "Press snapshot."),
    ("2026-03-18", "pres-2028-winner", "polymarket", "Marco Rubio", 11.0,
     "https://casinobeats.com/2026/03/18/gavin-newsom-jd-vance-see-chances-leading-parties-2028-sharply-decline/", "Press snapshot."),
    ("2026-03-18", "pres-2028-winner", "kalshi", "JD Vance", 19.2,
     "https://casinobeats.com/2026/03/18/gavin-newsom-jd-vance-see-chances-leading-parties-2028-sharply-decline/", "Press snapshot."),
    ("2026-03-18", "pres-2028-winner", "kalshi", "Gavin Newsom", 18.3,
     "https://casinobeats.com/2026/03/18/gavin-newsom-jd-vance-see-chances-leading-parties-2028-sharply-decline/", "Press snapshot."),
    ("2026-10-04", "gop-nominee-2028", "kalshi", "JD Vance", 45.0,
     "https://defirate.com/odds/republican-nominee/", "Aggregator quote flagged as possibly stale."),
    ("2026-10-04", "gop-nominee-2028", "polymarket", "JD Vance", 50.0,
     "https://defirate.com/odds/republican-nominee/", "Aggregator quote flagged as possibly stale."),
]


def seed_polls_frame() -> pd.DataFrame:
    rows = []
    for race_id, pollster, sponsor, start, end, n, pop, vals, url, notes in SEED_POLLS:
        assert race_id in config.RACE_BY_ID, race_id
        race = config.RACE_BY_ID[race_id]
        pid = make_poll_id(race_id, pollster, end, pop)
        for cand, pct in vals.items():
            assert cand in race.candidates, (race_id, cand)
            rows.append(dict(poll_id=pid, race_id=race_id, pollster=pollster, sponsor=sponsor,
                             start_date=start, end_date=end, sample_size=n, population=pop,
                             candidate=cand, pct=pct, source_url=url, source_type="seed",
                             notes=notes, fetched_at=FETCHED))
    return validate_polls(pd.DataFrame(rows, columns=POLL_COLUMNS))


def seed_markets_frame() -> pd.DataFrame:
    rows = [dict(snapshot_date=d, market_id=m, platform=p, outcome=o, price=pr, source_url=u,
                 source_type="seed", notes=n, fetched_at=FETCHED) for d, m, p, o, pr, u, n in SEED_MARKETS]
    return pd.DataFrame(rows, columns=MARKET_COLUMNS)


def write_seed() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    seed_polls_frame().to_csv(config.DATA_DIR / "polls.csv", index=False)
    seed_markets_frame().to_csv(config.DATA_DIR / "markets.csv", index=False)
    print("wrote", config.DATA_DIR / "polls.csv", "and markets.csv")


if __name__ == "__main__":
    write_seed()
