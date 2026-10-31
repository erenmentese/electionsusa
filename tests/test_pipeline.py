import json
from datetime import date

import pandas as pd
import pytest

from pipeline import average, build, config, scorecard
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
    assert len(tables) == 1  # only the matching matchup
    df0, urls0, heading0 = tables[0]
    rows = rows_from_table(df0, urls0, race, "https://en.wikipedia.org/wiki/x", heading0)
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


@pytest.mark.parametrize("pollster, sponsor, grade", [
    ("co", "efficient (R)", "B+"),               # co/efficient, not The New York Times/Siena College's A+
    ("Data", "", "B"),                           # Data for Progress, not Data Orbital's A/B
    ("Harvard", "Harris Poll/HarrisX", None),    # HarrisX is unrated, not Harvard University's B/C
    ("The Economist", "YouGov", "B+"),           # media sponsors listed first used to leave these unrated
    ("Reuters", "Ipsos", "B-"),
    ("CNN", "SSRS", "C+"),
    ("Washington Post", "ABC News/Ipsos", "B-"),  # run by Ipsos, not graded as "ABC News/The Washington Post"
    ("CBS News", "YouGov", "B+"),
    ("Fox News", "", "A"),                       # Beacon Research/Shaw & Co. Research
    ("NPR", "PBS/Marist University", "A"),       # rated as Marist College
    ("Hart Research Associates (D)", "Public Opinion Strategies (R)", "B+"),  # the NBC News poll
    ("Emerson College", "", "A-"),
    ("538 aggregate", "", None),
])
def test_grade_belongs_to_the_firm_that_ran_the_poll(pollster, sponsor, grade):
    grades = average._grade_lookup(scorecard.load_538()[1])
    assert average.pollster_grade(pollster, sponsor, grades) == grade


def test_weights_use_the_grade_the_table_shows():
    polls, _, ratings = build.load_data()
    grades = average._grade_lookup(ratings)
    for race in config.RACES:
        wide = average.to_wide(polls, race).assign(sample_size=600.0)  # leaves only the quality factor
        shown = [config.GRADE_WEIGHTS.get(average.pollster_grade(p, s, grades) or "", config.DEFAULT_GRADE_WEIGHT)
                 for p, s in zip(wide["pollster"], wide["sponsor"])]
        assert average.static_weights(wide, grades).round(6).tolist() == pd.Series(shown).round(6).tolist(), race.id


def test_frequency_damping_counts_polls_by_firm():
    race, d = config.RACE_BY_ID["generic-ballot-2026"], date(2026, 10, 20)
    polls = pd.DataFrame([
        dict(poll_id=f"p{i}", race_id=race.id, pollster=p, sponsor=s, start_date=d, end_date=d, sample_size=1000.0,
             population="RV", source_url="", notes="", candidate=c, pct=v)
        for i, (p, s) in enumerate([("The Economist", "YouGov"), ("Yahoo News", "YouGov"), ("Emerson College", "")])
        for c, v in (("Democrats", 48.0), ("Republicans", 44.0))])
    wide = average.to_wide(polls, race)
    grades = average._grade_lookup(scorecard.load_538()[1])
    damp = average.poll_weights(wide, d, race.half_life_days, grades) / average.static_weights(wide, grades)
    assert dict(zip(wide["pollster"], damp.round(3))) == {"The Economist": 0.707, "Yahoo News": 0.707, "Emerson College": 1.0}


def test_race_tables_show_the_firms_grade(site):
    rows = json.loads((site / "api" / "approval-trump-2.json").read_text())["polls"]
    economist = {r["grade"] for r in rows if r["pollster"] == "The Economist" and r["sponsor"] == "YouGov"}
    assert economist == {"B+"}


def test_seed_data_valid():
    df = seed_polls_frame()
    assert not df.empty
    assert df["source_url"].str.startswith("http").all()
    assert set(df["race_id"]) <= set(config.RACE_BY_ID)


def test_wikipedia_live_layouts_oct_2026():
    """Shapes seen on the live pages in Oct 2026: year-less dates under month headings,
    aggregator tables, 'Nationwide' headings shared by every matchup, 3-way tables,
    statewide approval tables and head-to-head tables on primary pages."""
    approval = config.RACE_BY_ID["approval-trump-2"]
    html = """
    <h2>Nationwide job approval ratings</h2><h3>Aggregate polls</h3><h4>Approval</h4>
    <table class="wikitable"><tr><th>Aggregator</th><th>Updated</th><th>Approve</th><th>Disapprove</th><th>Lead</th></tr>
      <tr><td>Ballotpedia</td><td>October 29, 2026</td><td>38.0%</td><td>60.0%</td><td>−22.0%</td></tr></table>
    <h3>2026</h3><h4>October 2026</h4>
    <table class="wikitable"><tr><th>Poll source</th><th>Date</th><th>Sample size[a]</th><th>MoE</th><th>Approve</th><th>Disapprove</th><th>Unsure/Other</th><th>Net</th></tr>
      <tr><td><a href="https://en.wikipedia.org/wiki/Harvard">Harvard</a>/<a href="https://harvardharrispoll.com/x.pdf">Harris</a></td><td>October 24–26</td><td>2,700 RV</td><td>± 1.9%</td><td>39%</td><td>59%</td><td>3%</td><td>−20%</td></tr>
      <tr><td>Reuters/Ipsos</td><td>September 28 – October 4</td><td>1,100 A</td><td>± 3%</td><td>41%</td><td>56%</td><td>3%</td><td>−15%</td></tr></table>
    <h2>Statewide job approval ratings</h2><h3>Alaska</h3>
    <table class="wikitable"><tr><th>Poll source</th><th>Date</th><th>Sample size</th><th>Approve</th><th>Disapprove</th></tr>
      <tr><td>Alaska Survey</td><td>October 1–3</td><td>500 RV</td><td>52%</td><td>44%</td></tr></table>"""
    tables = tables_for_race(html, approval)
    assert len(tables) == 1
    rows = rows_from_table(*tables[0][:2], approval, "https://en.wikipedia.org/wiki/x", tables[0][2])
    df = pd.DataFrame(rows)
    assert len(df) == 4
    hh = df[df.pollster.str.startswith("Harvard")].iloc[0]
    assert hh.end_date == "2026-10-26" and hh.start_date == "2026-10-24" and hh.population == "RV"
    assert hh.source_url == "https://harvardharrispoll.com/x.pdf"
    ri = df[df.pollster.str.startswith("Reuters")].iloc[0]
    assert ri.start_date == "2026-09-28" and ri.end_date == "2026-10-04"

    general = config.RACE_BY_ID["pres-2028-vance-newsom"]
    html = """
    <h2>Polling</h2><h3>Nationwide</h3>
    <table class="wikitable"><tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>Vance (R)</th><th>Harris (D)</th><th>Undecided</th></tr>
      <tr><td>Emerson College</td><td>August 16–17, 2026</td><td>1,000 (LV)</td><td>45%</td><td>49%</td><td>6%</td></tr></table>
    <table class="wikitable"><tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>Vance (R)</th><th>Newsom (D)</th><th>Undecided</th></tr>
      <tr><td>The Bulwark/Pablo Torre</td><td>October 10–14, 2026</td><td>1,417 (A)</td><td>44%</td><td>47%</td><td>9%</td><td></td><td></td></tr></table>
    <table class="wikitable"><tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>Vance (R)</th><th>Newsom (D)</th><th>Rodgers (I)</th><th>Undecided</th></tr>
      <tr><td>The Bulwark/Pablo Torre</td><td>October 10–14, 2026</td><td>1,417 (A)</td><td>40%</td><td>42%</td><td>8%</td><td>10%</td></tr></table>"""
    tables = tables_for_race(html, general)
    assert len(tables) == 1  # the two-way Vance/Newsom table only
    rows = rows_from_table(*tables[0][:2], general, "u", tables[0][2])
    assert {r["candidate"] for r in rows} == {"JD Vance", "Gavin Newsom"} and len(rows) == 2
    assert rows[0]["sponsor"] == "Pablo Torre"

    primary = config.RACE_BY_ID["gop-primary-2028"]
    html = """
    <h2>Polling aggregation</h2>
    <table class="wikitable"><tr><th>Aggregator</th><th>Updated</th><th>Ron DeSantis</th><th>Marco Rubio</th><th>JD Vance</th></tr>
      <tr><td>270toWin</td><td>August 14, 2026</td><td>2.5%</td><td>10%</td><td>60%</td></tr></table>
    <h2>Polling</h2><h3>2026</h3>
    <table class="wikitable"><tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>Ted Cruz</th><th>Ron DeSantis</th><th>Nikki Haley</th><th>Marco Rubio</th><th>JD Vance</th><th>Other/Undecided</th></tr>
      <tr><td>Clarity Campaign Labs</td><td>October 15–21, 2026</td><td>413 (LV)</td><td>3%</td><td>5%</td><td>2%</td><td>12%</td><td>58%</td><td>20%</td></tr></table>
    <h2>Hypothetical polling</h2><h3>Vance vs. Rubio</h3>
    <table class="wikitable"><tr><th>Polling firm</th><th>Date(s) administered</th><th>Sample size</th><th>JD Vance</th><th>Marco Rubio</th></tr>
      <tr><td>Overton Insights</td><td>May 16–20, 2026</td><td>1,377 (RV)</td><td>61%</td><td>23%</td></tr></table>"""
    tables = tables_for_race(html, primary)
    assert len(tables) == 1
    rows = rows_from_table(*tables[0][:2], primary, "u", tables[0][2])
    assert {r["candidate"] for r in rows} == {"Ron DeSantis", "Nikki Haley", "Marco Rubio", "JD Vance", "Other/Undecided"}

    generic = config.RACE_BY_ID["generic-ballot-2026"]
    html = """
    <h2>Federal elections</h2><h3>Generic congressional ballot aggregate polls</h3>
    <table class="wikitable"><tr><th>Source of poll aggregation</th><th>Dates administered</th><th>Dates updated</th><th>Republicans</th><th>Democrats</th><th>Margin</th></tr>
      <tr><td>Decision Desk HQ</td><td>January 9, 2025 – October 26, 2026</td><td>October 29, 2026</td><td>41.8%</td><td>51.2%</td><td>D +9.4</td></tr></table>
    <h2>Polling</h2><h3>2025–2026</h3>
    <table class="wikitable"><tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>Margin of error</th><th>Democratic</th><th>Republican</th><th>Other/Undecided</th><th>Lead</th></tr>
      <tr><td rowspan="2">Tufts University/YouGov</td><td rowspan="2">October 23–27, 2026</td><td>499 (LV)</td><td>± 4.6%</td><td>52%</td><td>40%</td><td>8%</td><td>12%</td></tr>
      <tr><td>1,000 (A)</td><td>± 3.6%</td><td>47%</td><td>36%</td><td>17%</td><td>11%</td></tr></table>"""
    tables = tables_for_race(html, generic)
    assert len(tables) == 1
    rows = rows_from_table(*tables[0][:2], generic, "u", tables[0][2])
    df = pd.DataFrame(rows)
    assert set(df.candidate) == {"Democrats", "Republicans"} and len(df) == 4
    assert set(df.population) == {"LV", "A"}
