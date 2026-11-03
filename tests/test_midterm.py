import re
from datetime import date

import pytest

from pipeline import build, config


@pytest.fixture(scope="module")
def election_day(tmp_path_factory):
    """The site as built on Election Day, November 3, 2026."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "DIST_DIR", tmp_path_factory.mktemp("eday") / "dist")
        yield build.build(date(2026, 11, 3))


def test_hub_lists_every_state_with_closing_time_and_official_link(election_day):
    html = (election_day / "2026" / "index.html").read_text()
    rows = re.findall(r"<tr><td><a href=\"/states/[^\"]+/\">", html)
    assert len(rows) == 51
    assert "6 p.m." in html and "midnight (Nov 4)" in html
    assert "Final generic ballot average" in html and "FAQPage" in html
    assert "does not call races" in html  # results are linked, not reported


def test_hub_leads_the_nav_and_is_in_footer_and_sitemap(election_day):
    home = (election_day / "index.html").read_text()
    nav = re.search(r'<nav class="nav"[^>]*>(.*?)</nav>', home, re.S).group(1)
    assert re.findall(r'href="([^"]+)"', nav)[0] == "/2026/"
    assert 'site-footer' in home and '<a href="/2026/">2026 midterms</a>' in home
    assert "<loc>https://electionsusa.org/2026/</loc><lastmod>2026-11-03</lastmod>" in (election_day / "sitemap.xml").read_text()


def test_countdown_says_election_day_not_zero_days(election_day):
    html = (election_day / "countdown" / "index.html").read_text()
    assert "0 days until" not in html
    assert "Today is Election Day" in html and 'href="/2026/"' in html


def test_generic_ballot_page_has_pending_result_section(election_day):
    html = (election_day / "2026" / "generic-ballot" / "index.html").read_text()
    assert 'id="vs-result"' in html and "Final average vs. House popular vote" in html and "pending" in html


def test_about_promises_comparison_with_results(election_day):
    html = (election_day / "about" / "index.html").read_text()
    assert "we do not report election results" not in html
    assert "compare final polls with official results" in html


def test_finder_sends_house_and_results_queries_to_the_hub(election_day):
    import json
    index = json.loads((election_day / "api" / "search-index.json").read_text())

    def score(e, q):  # mirrors site.js
        stop = {"the", "is", "who", "what", "in", "of", "a", "an", "vs", "are", "does", "do", "how", "many", "until", "to", "for", "and"}
        hay = (e["t"] + " " + e["q"] + " " + e["s"]).lower()
        return sum(3 if t in e["t"].lower() else 1 if t in hay else 0 for t in q.lower().split() if t not in stop)
    for q in ("who won the house today", "senate results", "midterm"):
        best = max(index, key=lambda e: score(e, q))
        assert best["u"] == "/2026/", q


def test_countdown_after_the_midterms_shows_results_card():
    env = build.Environment(loader=build.FileSystemLoader(str(config.TEMPLATE_DIR)))
    env.filters.update(short=build.short_name, signed=build.signed)
    env.globals.update(site=config.SITE, nav=[], days_to_midterm=-2, days_to_election=733, races=[],
                       election_day=config.ELECTION_DAY_2028, build_date="", build_iso="", year=2026)
    html = env.get_template("countdown.html").render(path="/countdown/")
    assert "results and what the polls said" in html and "days until the 2026" not in html
