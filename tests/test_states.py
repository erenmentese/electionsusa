import json
import re

import pandas as pd
import pytest

from pipeline import history, usmap

# Electoral votes as pledged by each state's result (faithless electors ignored): (Dem, Rep)
PLEDGED = {1976: (297, 241), 1980: (49, 489), 1984: (13, 525), 1988: (112, 426), 1992: (370, 168),
           1996: (379, 159), 2000: (267, 271), 2004: (252, 286), 2008: (365, 173), 2012: (332, 206),
           2016: (232, 306), 2020: (306, 232), 2024: (226, 312)}


@pytest.fixture(scope="module")
def results():
    return history.load()


def test_every_election_reproduces_the_electoral_college(results):
    states, nation = results
    assert len(states) == 51 and all(len(st.years) == 13 for st in states.values())
    for year, (d, r) in PLEDGED.items():
        assert (nation[year].ev_dem, nation[year].ev_rep) == (d, r), year
        assert sum(st.by_year(year).ev for st in states.values()) == 538, year
    # 2024 national totals match the FEC's certified count exactly
    assert (nation[2024].rep_votes, nation[2024].dem_votes) == (77_302_580, 75_017_613)


def test_state_facts(results):
    states, nation = results
    pa = states["PA"]
    assert (pa.latest.ev, pa.latest.margin_label, history.fmt_lean(pa.lean(nation))) == (19, "Trump +1.7", "R+0.2")
    assert pa.picked_winner(nation) == 11 and pa.last_win("D") == 2020 and pa.streak() == 1
    assert (states["ME"].latest.ev_dem, states["ME"].latest.ev_rep) == (3, 1)
    assert (states["NE"].latest.ev_dem, states["NE"].latest.ev_rep) == (1, 4)
    assert states["DC"].last_win("R") is None
    assert states["UT"].by_year(2016).other == "Evan McMullin"
    assert history.answer_sentence(pa, nation) == (
        "Pennsylvania voted for Donald Trump in 2024, 50.4% to 48.7% (Trump +1.7); all 19 of its electoral votes "
        "went to Trump. It has backed the winning candidate in 11 of the last 13 presidential elections.")
    assert history.national_sentence(states, nation, 2024).startswith(
        "Donald Trump won the 2024 presidential election with 312 electoral votes to Kamala Harris's 226, carrying 31 of the 50 states.")


def test_names_and_labels():
    assert history.display_name('CLARK, EDWARD ""ED""') == "Ed Clark"
    assert history.display_name("MACBRIDE, ROGER") == "Roger MacBride"
    assert history.display_name("KENNEDY, ROBERT F. JR") == "Robert F. Kennedy Jr."
    assert history.fmt_margin(-6.85, "Kamala Harris", "Donald Trump") == "Harris +6.8"
    assert [usmap.shade(m) for m in (-20, -10, -1, 0.5, 7, 30)] == ["d3", "d2", "d1", "r1", "r2", "r3"]
    assert history.electoral_votes_census(1980) == 1970 and history.electoral_votes_census(2028) == 2020


def test_map_paths(results):
    states, _ = results
    paths = usmap.state_paths()
    assert set(paths) == {st.fips for st in states.values()}
    assert all(re.fullmatch(r"(M-?\d+,-?\d+l[-\d, ]+z)+", d) for d in paths.values())
    m = usmap.map_context(states, 2024)
    assert len(m["shapes"]) == 51 and [b["po"] for b in m["boxes"]] == usmap.BOXED


def test_state_pages(site):
    hub = (site / "states" / "index.html").read_text()
    assert hub.count('href="/states/') >= 51 * 2  # map links + table links
    page = (site / "states" / "pennsylvania" / "index.html").read_text()
    blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
    crumbs = next(b for b in blocks if b.get("@type") == "BreadcrumbList")["itemListElement"]
    assert [c["name"] for c in crumbs] == ["Home", "Results by state", "Pennsylvania"]
    assert any(b.get("@type") == "Dataset" for b in blocks)
    assert "og/states/pennsylvania.png" in page and (site / "og" / "states" / "pennsylvania.png").exists()
    assert len(list((site / "states").glob("*/index.html"))) == 51

    home = (site / "index.html").read_text()
    assert home.count("<path class=\"st ") == 51 and "Where 2028 starts" in home

    csv = pd.read_csv(site / "data" / "president-by-state.csv")
    assert len(csv) == 51 * 13 and csv.groupby("year")["electoral_votes"].sum().eq(538).all()
    sitemap = (site / "sitemap.xml").read_text()
    assert "https://electionsusa.org/states/pennsylvania/" in sitemap and "https://electionsusa.org/states/</loc>" in sitemap
