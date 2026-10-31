import re

import pytest

from pipeline import pollsters, scorecard


@pytest.mark.parametrize("pollster, sponsor, firm", [
    ("The Economist", "YouGov", "YouGov"),
    ("Reuters", "Ipsos", "Ipsos"),
    ("CNN", "SSRS", "SSRS"),
    ("New York Times", "Siena College", "The New York Times/Siena College"),
    ("Washington Post", "ABC News/Ipsos", "Ipsos"),
    ("NPR", "PBS/Marist University", "Marist University"),
    ("Harvard", "Harris Poll/HarrisX", "HarrisX"),
    ("co", "efficient (R)", "co/efficient"),
    ("Data", "", "Data for Progress"),
    ("Atlas Intel", "", "AtlasIntel"),
    ("McLauglin & Associates", "", "McLaughlin & Associates"),
    ("Morning Consult", "Politico", "Morning Consult"),
])
def test_polls_are_credited_to_the_firm_that_ran_them(pollster, sponsor, firm):
    assert pollsters.firm(pollster, sponsor) == firm


def test_party_tags():
    assert pollsters.resolve("Cygnal (R)") == ("Cygnal", "R")
    assert pollsters.resolve("I&I", "TIPP Insights (R)") == ("TIPP Insights", "R")
    assert pollsters.resolve("Beacon Research (D)", "Shaw & Co. Research (R)") == (pollsters.BEACON, "")  # bipartisan
    assert pollsters.resolve("538 aggregate") is None


def test_rated_answer_sentence():
    rated = scorecard.historical_scorecard()
    nyt = pollsters.registry([], rated)[pollsters.key(pollsters.NYT_SIENA)]
    assert pollsters.answer_sentence(nyt, len(rated)) == (
        "The New York Times/Siena College's 95 polls in the final three weeks of 2016–2022 races missed the final "
        "margin by 4.0 points on average, ranking 2nd of 69 pollsters on the ElectionsUSA scorecard. On average its "
        "polls leaned 1.2 points toward Democrats, and 75% had the eventual winner ahead.")
    assert [pollsters.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 69)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "69th"]


def test_pollster_pages(site):
    pages = {p.parent.name for p in (site / "pollsters").glob("*/index.html")}
    assert len(pages) >= 69  # every rated pollster, plus active unrated ones

    yougov = (site / "pollsters" / "yougov" / "index.html").read_text()
    assert "How accurate is YouGov?" in yougov and "By election year" in yougov
    assert "The Economist" in yougov  # Economist/YouGov polls sit on YouGov's page
    assert '"name": "Pollster scorecard"' in yougov  # breadcrumb

    mcl = (site / "pollsters" / "mclaughlin-and-associates" / "index.html").read_text()
    assert "McLaughlin &amp; Associates polls" in mcl and "not on the accuracy scorecard yet" in mcl
    for slug in pages:
        html = (site / "pollsters" / slug / "index.html").read_text()
        if "not on the accuracy scorecard yet" in html:  # unrated pages need enough polls not to be thin
            rows = html.split('id="pollster-polls"')[1].split("</table>")[0].count("<tr") - 1
            assert rows >= pollsters.MIN_POLLS, slug

    # every rated row, race-table pollster and finder entry points at a page that exists
    scorecard_html = (site / "pollsters" / "index.html").read_text()
    assert scorecard_html.count('<td><a href="/pollsters/') >= 69
    generic = (site / "2026" / "generic-ballot" / "index.html").read_text()
    assert 'href="/pollsters/yougov/"' in generic
    for page in site.rglob("*.html"):
        for slug in re.findall(r'href="/pollsters/([^"#/]+)/"', page.read_text()):
            assert slug in pages, (page, slug)

    sitemap = (site / "sitemap.xml").read_text()
    assert "https://electionsusa.org/pollsters/yougov/</loc><lastmod>" in sitemap
    assert "https://electionsusa.org/pollsters/selzer-and-co/</loc></url>" in sitemap  # no current polls, no lastmod
