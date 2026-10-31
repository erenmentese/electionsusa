import json
import re
from datetime import date

from PIL import Image

from pipeline import build, config
from pipeline.average import RaceAverage

AS_OF = date(2026, 10, 31)


def ra(race_id, values, n=12):
    race = config.RACE_BY_ID[race_id]
    margin = values[race.candidates[0]] - values[race.candidates[1]] if len(race.candidates) == 2 else None
    return RaceAverage(race_id=race_id, as_of=AS_OF, values=values, n_polls=n, margin=margin)


def answer(race_id, values, n=12):
    return build.answer_sentence(config.RACE_BY_ID[race_id], ra(race_id, values, n), AS_OF)


def test_answer_sentences():
    assert answer("approval-trump-2", {"Approve": 42.04, "Disapprove": 54.3}) == (
        "Trump's job approval stands at 42.0% approve and 54.3% disapprove (net −12.3) "
        "in the ElectionsUSA average of 12 polls, as of October 31, 2026.")
    assert answer("pres-2028-vance-newsom", {"JD Vance": 44.8, "Gavin Newsom": 46.0}, n=1) == (
        "Gavin Newsom leads JD Vance 46.0% to 44.8% in a hypothetical 2028 matchup, "
        "according to the ElectionsUSA average of 1 poll, as of October 31, 2026.")
    assert answer("generic-ballot-2026", {"Democrats": 47.1, "Republicans": 44.0}).startswith(
        "Democrats lead Republicans 47.1% to 44.0% on the generic congressional ballot")
    assert answer("dem-primary-2028", {"Gavin Newsom": 24.0, "Kamala Harris": 18.2, "Pete Buttigieg": 9.5,
                                       "Cory Booker": 3.0, "Other/Undecided": 30.0}) == (
        "Gavin Newsom leads the 2028 Democratic primary with 24.0% in the ElectionsUSA average of 12 national polls, "
        "ahead of Kamala Harris (18.2%) and Pete Buttigieg (9.5%), as of October 31, 2026.")


def test_answer_sentence_ties_and_empty():
    # equal after rounding reads as a tie, never "leads 46.0% to 46.0%"
    assert answer("pres-2028-vance-newsom", {"JD Vance": 46.04, "Gavin Newsom": 45.97}).startswith(
        "JD Vance and Gavin Newsom are tied at 46.0%")
    assert answer("gop-primary-2028", {"JD Vance": 30.0, "Marco Rubio": 30.02, "Ron DeSantis": 10.0}).startswith(
        "Marco Rubio and JD Vance are tied for the lead in the 2028 Republican primary at 30.0%")
    assert build.answer_sentence(config.RACE_BY_ID["pres-2028-vance-newsom"], RaceAverage("x", AS_OF), AS_OF) == ""


def test_build_seo_output(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIST_DIR", tmp_path / "dist")
    dist = build.build(AS_OF)

    # every page carries valid JSON-LD (no HTML entities leaking into JSON) and an og:image that exists
    for page in dist.rglob("*.html"):
        html = page.read_text()
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            assert "&#" not in block
            json.loads(block)
        og = re.search(r'og:image" content="https://electionsusa\.org(/og/[^"?]+)\?v=2026-10-31"', html)
        assert og, page
        img = Image.open(dist / og.group(1).lstrip("/"))
        assert img.size == (1200, 630)

    race_html = (dist / "approval" / "trump" / "index.html").read_text()
    assert '"@type": "BreadcrumbList"' in race_html and '"@type": "Dataset"' in race_html
    assert "og/approval-trump-2.png" in race_html
    assert "in the ElectionsUSA average of" in race_html

    # long poll tables fold behind "See all" but keep every row in the HTML; short ones don't fold
    rows = re.findall(r"<tr( class=\"fold\")?>", race_html.split('id="all-polls"')[1].split("</table>")[0])
    assert len(rows) > 15 and [bool(r) for r in rows].count(False) == 13  # header + 12 newest polls
    assert "data-fold-toggle" in race_html
    assert "data-fold-toggle" not in (dist / "2028" / "president" / "vance-vs-buttigieg" / "index.html").read_text()

    # lastmod only where there is a real date, never in the future
    sitemap = (dist / "sitemap.xml").read_text()
    urls = dict(re.findall(r"<loc>https://electionsusa\.org([^<]*)</loc>(?:<lastmod>([^<]*)</lastmod>)?", sitemap))
    assert urls["/methodology/"] == "" and urls["/about/"] == ""
    assert urls["/privacy/"] == "2026-10-29"
    assert all(d <= AS_OF.isoformat() for d in urls.values() if d)
