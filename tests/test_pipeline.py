from datetime import date

import pandas as pd

from pipeline import average, config
from pipeline.fetch_wikipedia import match_candidate, parse_date_range, parse_sample, rows_from_table, tables_for_race
from pipeline.seed_data import seed_polls_frame
from pipeline.schema import validate_polls


def test_parse_date_ranges():
    assert parse_date_range("Oct 13–14, 2025") == (date(2025, 10, 13), date(2025, 10, 14))
    assert parse_date_range("September 28 – October 4, 2026") == (date(2026, 9, 28), date(2026, 10, 4))
    assert parse_date_range("Dec 30, 2025 – Jan 2, 2026") == (date(2025, 12, 30), date(2026, 1, 2))
    assert parse_date_range("Oct 19, 2026") == (date(2026, 10, 19), date(2026, 10, 19))
    assert parse_date_range("garbage") == (None, None)


def test_parse_sample():
    assert parse_sample("1,000 (RV)") == (1000.0, "RV")
    assert parse_sample("1,679 (A)") == (1679.0, "A")
    assert parse_sample("–") == (None, "")


def test_candidate_matching():
    race = config.RACE_BY_ID["gop-primary-2028"]
    assert match_candidate("Vance", race) == "JD Vance"
    assert match_candidate("Rubio[a]", race) == "Marco Rubio"
    assert match_candidate("Undecided", race) == "Other/Undecided"
    assert match_candidate("Sample size", race) is None


def test_wikipedia_table_parsing():
    race = config.RACE_BY_ID["pres-2028-vance-newsom"]
    html = """
    <h3>Vance vs. Newsom</h3>
    <table class="wikitable">
      <tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>Margin of error</th><th>JD Vance (R)</th><th>Gavin Newsom (D)</th><th>Other/Undecided</th></tr>
      <tr><td><a href="https://example.com/poll1">Emerson College</a></td><td>Oct 13–14, 2025</td><td>1,000 (RV)</td><td>± 3.0%</td><td>46%</td><td>45%</td><td>9%</td></tr>
      <tr><td><a href="https://example.com/poll2">Zogby Analytics</a></td><td>Jul 1–4, 2026</td><td>1,003 (LV)</td><td>± 3.1%</td><td>45.1%</td><td>38.1%</td><td>–</td></tr>
    </table>
    <h3>Vance vs. Buttigieg</h3>
    <table class="wikitable">
      <tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>JD Vance (R)</th><th>Pete Buttigieg (D)</th></tr>
      <tr><td>Other Poll</td><td>Jul 1–4, 2026</td><td>900 (LV)</td><td>44%</td><td>41%</td></tr>
    </table>"""
    tables = tables_for_race(html, race)
    assert len(tables) == 1  # only the matching matchup heading
    rows = rows_from_table(*tables[0], race, "https://en.wikipedia.org/wiki/x")
    df = validate_polls(pd.DataFrame(rows))
    assert set(df["candidate"]) == {"JD Vance", "Gavin Newsom"}
    assert len(df) == 4
    em = df[(df.pollster == "Emerson College") & (df.candidate == "JD Vance")].iloc[0]
    assert em.pct == 46 and em.sample_size == 1000 and em.population == "RV"
    assert em.source_url == "https://example.com/poll1"


def test_average_is_weighted_and_bounded():
    polls = seed_polls_frame()
    race = config.RACE_BY_ID["generic-ballot-2026"]
    ra = average.compute_race(polls, race, ratings=None, as_of=date(2026, 10, 25))
    assert ra.values["Democrats"] > ra.values["Republicans"]
    assert 35 <= ra.values["Republicans"] <= 41 and 44 <= ra.values["Democrats"] <= 47
    # the January Rasmussen poll should carry near-zero weight nine months later
    assert ra.n_polls == 2
    assert ra.trend["Democrats"][-1][0] == date(2026, 10, 25)


def test_trend_has_no_lookahead():
    polls = seed_polls_frame()
    race = config.RACE_BY_ID["pres-2028-vance-newsom"]
    ra = average.compute_race(polls, race, ratings=None, as_of=date(2026, 10, 25))
    # before the Zogby poll (July 2026) the average must equal the Emerson-only value
    early = [v for d, v in ra.trend["JD Vance"] if d < date(2026, 7, 4)]
    assert early and all(44 <= v <= 46.5 for v in early)


def test_seed_data_valid():
    df = seed_polls_frame()
    assert not df.empty
    assert df["source_url"].str.startswith("http").all()
    assert set(df["race_id"]) <= set(config.RACE_BY_ID)
