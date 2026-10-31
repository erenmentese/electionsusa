from datetime import date

import pandas as pd

from pipeline import config
from pipeline.check_data import check, report, structure

TODAY = date(2026, 10, 31)


def poll(race_id, end, values, poll_id=None):
    return [dict(poll_id=poll_id or f"{race_id}-{end}", race_id=race_id, pollster="Test Poll", sponsor="", start_date=end,
                 end_date=end, sample_size=1000, population="RV", candidate=c, pct=v, source_url="", source_type="manual",
                 notes="", fetched_at="") for c, v in values.items()]


def healthy_polls(**overrides):
    ends = {"approval-trump-2": "2026-10-28", "dem-primary-2028": "2026-10-20", "gop-primary-2028": "2026-10-20",
            "generic-ballot-2026": "2026-10-27", "pres-2028-vance-newsom": "2026-08-01"} | overrides
    rows = poll("approval-trump-2", ends["approval-trump-2"], {"Approve": 42, "Disapprove": 54})
    rows += poll("dem-primary-2028", ends["dem-primary-2028"], {"Kamala Harris": 25, "Gavin Newsom": 20})
    rows += poll("gop-primary-2028", ends["gop-primary-2028"], {"JD Vance": 45, "Marco Rubio": 15})
    rows += poll("generic-ballot-2026", ends["generic-ballot-2026"], {"Democrats": 48, "Republicans": 44})
    rows += poll("pres-2028-vance-newsom", ends["pres-2028-vance-newsom"], {"JD Vance": 44, "Gavin Newsom": 45})
    return pd.DataFrame(rows)


MARKETS = pd.DataFrame([dict(snapshot_date="2026-10-31", market_id="pres-2028-winner", platform="polymarket",
                             outcome="JD Vance", price=30, source_url="", source_type="api", notes="")])


def test_healthy_data_has_no_problems():
    problems, status = check(healthy_polls(), MARKETS, TODAY)
    assert problems == []
    assert any(s.startswith("Trump approval: latest poll ended 2026-10-28") for s in status)
    assert "All good" in report(problems, status, pd.Timestamp("2026-10-31 12:00").to_pydatetime())


def test_stale_series_and_failed_steps_are_problems():
    problems, _ = check(healthy_polls(**{"approval-trump-2": "2026-10-20"}), MARKETS, TODAY, fetch="failure", tests="failure")
    text = " ".join(problems)
    assert "fetch step failed" in text and "Tests failed" in text and "No new Trump approval poll for 11 days" in text
    # rarely polled general-election matchups never alarm; stale markets do
    old_markets = MARKETS.assign(snapshot_date="2026-10-25")
    problems, _ = check(healthy_polls(**{"pres-2028-vance-newsom": "2026-01-01"}), old_markets, TODAY)
    assert problems == ["No prediction-market snapshot since 2026-10-25 (alert after 2 days)."]


def test_generic_ballot_stops_alarming_after_the_midterm():
    problems, _ = check(healthy_polls(), MARKETS.assign(snapshot_date="2026-11-30"), date(2026, 11, 30))
    assert not any("Generic ballot" in p for p in problems)


def test_parser_breakage_signals():
    bad = pd.concat([
        healthy_polls(),
        pd.DataFrame(poll("approval-trump-2", "2027-03-01", {"Approve": 40, "Disapprove": 50}, poll_id="future")),
        pd.DataFrame(poll("generic-ballot-2026", "2026-10-29", {"Democrats": 60, "Republicans": 58}, poll_id="mixup")),
        pd.DataFrame(poll("approval-trump-2", "not a date", {"Approve": 140}, poll_id="junk")),
        pd.DataFrame(poll("senate-2026-xx", "2026-10-29", {"A": 50}, poll_id="unknown")),
    ])
    text = " ".join(check(bad, MARKETS, TODAY)[0])
    assert "1 row(s)" in text and "end in the future" in text and "more than 105%" in text and "senate-2026-xx" in text


def test_committed_data_is_well_formed():
    # runs in the workflow on freshly fetched data, before it is committed
    assert structure(pd.read_csv(config.DATA_DIR / "polls.csv"), date.today()) == []
