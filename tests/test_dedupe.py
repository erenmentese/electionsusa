import pandas as pd

from pipeline import check_data, dedupe
from pipeline.schema import validate_polls


def poll(pid, pollster, sponsor, pop, dem, rep, n=1000, start="2026-10-16", end="2026-10-19", race="generic-ballot-2026"):
    base = dict(poll_id=pid, race_id=race, pollster=pollster, sponsor=sponsor, start_date=start, end_date=end,
                sample_size=n, population=pop, source_url="", source_type="wikipedia", notes="", fetched_at="")
    return [base | dict(candidate="Democrats", pct=dem), base | dict(candidate="Republicans", pct=rep)]


def frame(*polls):
    return validate_polls(pd.DataFrame([row for p in polls for row in p]))


def test_same_poll_listed_twice_counts_once():
    # the cases from the November 2026 audit: sponsor and pollster swapped, "Reuters/Ipsos" vs "Reuters" + "Ipsos"
    df = frame(poll("a", "Deseret News and Hinckley Institute of Politics", "Morning Consult", "RV", 48, 44, 2050),
               poll("b", "Morning Consult", "Deseret News and Hinckley Institute of Politics", "RV", 48, 44, 2050),
               poll("c", "Reuters/Ipsos", "", "RV", 50, 41, 1279),
               poll("d", "Reuters", "Ipsos", "RV", 50.4, 41, 1279))
    drop = dedupe.plan(df)
    assert sorted(v[0] for v in drop.values()) == ["copy", "copy"]
    assert dedupe.collapse(df)["poll_id"].nunique() == 2


def test_one_population_per_poll_likely_voters_first():
    df = frame(poll("lv", "Focaldata", "Financial Times", "LV", 51, 42, 2090),
               poll("rv", "Focaldata", "Financial Times", "RV", 50, 42, 2163),
               poll("a", "Focaldata", "Financial Times", "A", 47, 39, 2444))
    assert set(dedupe.collapse(df)["poll_id"]) == {"lv"}
    assert {v[0] for v in dedupe.plan(df).values()} == {"population"}


def test_different_polls_by_one_firm_both_count():
    # same firm and days but different media partners or different numbers: two polls
    df = frame(poll("wapo", "Washington Post", "Ipsos", "A", 40, 55, 1206, "2025-02-13", "2025-02-18"),
               poll("reut", "Reuters", "Ipsos", "A", 44, 51, 4145, "2025-02-13", "2025-02-18"),
               poll("x", "Strength In Numbers", "Verasight", "A", 47, 43),
               poll("y", "The Argument", "Verasight", "RV", 49, 44))
    assert dedupe.plan(df) == {}


def test_spelling_variants_resolve_to_one_pollster():
    df = frame(poll("z1", "Zogby Analytics", "", "LV", 45.1, 38.1, 1003, race="pres-2028-vance-newsom"),
               poll("z2", "Zogby", "", "LV", 45, 38, 1003, race="pres-2028-vance-newsom"))
    assert set(df["pollster"]) == {"Zogby Analytics"}
    assert set(validate_polls(pd.DataFrame(poll("t", "Tuft Public Opinion Lab", "YouGov", "LV", 50, 44)))["pollster"]) == {"Tufts University"}


def test_check_data_reports_zero_groups_after_dedupe():
    df = frame(poll("lv", "Focaldata", "Financial Times", "LV", 51, 42), poll("rv", "Focaldata", "Financial Times", "RV", 50, 42),
               poll("a", "Reuters/Ipsos", "", "RV", 50, 41), poll("b", "Reuters", "Ipsos", "RV", 50, 41))
    markets = pd.DataFrame([dict(snapshot_date="2026-10-19", market_id="x", platform="polymarket", outcome="y", price=50)])
    problems, status = check_data.check(df, markets, pd.Timestamp("2026-10-20").date())
    assert any("appear twice" in p for p in problems)  # the raw file holds a copy
    assert any(s.startswith("Duplicate groups feeding the averages: 0 (1 copies and 1 extra populations") for s in status)
