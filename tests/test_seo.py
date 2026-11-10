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


def test_build_seo_output(site):
    dist = site

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
    # dated, number-first titles; an FAQ marked up as FAQPage; links to the other averages
    assert re.search(r"<title>Trump Approval Rating Today: \d+\.\d% \(Oct \d+, 2026\)</title>", race_html)  # too long for the suffix
    assert '"@type": "FAQPage"' in race_html and "What is Trump&#39;s approval rating today?" in race_html
    assert 'class="related"' in race_html and 'href="/2026/generic-ballot/"' in race_html

    # long poll tables render the 25 newest polls and hold the rest in a <template> until "See all"; short ones don't fold
    table = race_html.split('id="all-polls"')[1].split("</table>")[0]
    shown, held = table.split("<template data-fold-rows>")
    assert shown.count("<tr") == 26 and held.count('<tr class="fold">') > 0  # header + 25 newest polls
    assert "</template>" in held
    assert "data-fold-toggle" in race_html
    assert "data-fold-toggle" not in (dist / "2028" / "president" / "vance-vs-buttigieg" / "index.html").read_text()

    # every page carries the date its content last changed, never in the future
    sitemap = (dist / "sitemap.xml").read_text()
    urls = dict(re.findall(r"<loc>https://electionsusa\.org([^<]*)</loc>(?:<lastmod>([^<]*)</lastmod>)?", sitemap))
    assert all(urls.values()), [u for u, d in urls.items() if not d]
    assert urls["/states/"] == "2026-10-31" and urls["/methodology/"] == AS_OF.isoformat()  # capped at the build date
    assert all(d <= AS_OF.isoformat() for d in urls.values())
    # the on-page date and the Dataset's dateModified are the same value
    approval = (dist / "approval" / "trump" / "index.html").read_text()
    shown = re.search(r'latest poll <time datetime="([^"]+)"', approval).group(1)
    assert f'"dateModified": "{shown}"' in approval and urls["/approval/trump/"] == shown
    assert "Site rebuilt" in approval


def test_short_name_keeps_generational_suffix():
    assert build.short_name("Donald Trump Jr.") == "Trump Jr."
    assert build.short_name("Robert F. Kennedy Jr.") == "Kennedy Jr."
    assert build.short_name("JD Vance") == "Vance"


def test_titles_say_today_only_for_fresh_polls():
    from datetime import date
    from pipeline import average, config
    race = config.RACE_BY_ID["pres-2028-vance-newsom"]
    ra = average.RaceAverage(race_id=race.id, as_of=date(2026, 11, 3), values={"JD Vance": 40.2, "Gavin Newsom": 43.6},
                             margin=-3.4, latest_end_date=date(2026, 10, 14))
    assert build.seo_title(race, ra, date(2026, 11, 3)) == "Vance vs. Newsom 2028 Polls: Newsom +3.4 (Oct 14, 2026)"
    assert build.seo_title(race, ra, date(2026, 10, 18)) == "Vance vs. Newsom 2028 Polls Today: Newsom +3.4 (Oct 14, 2026)"
    gen = config.RACE_BY_ID["generic-ballot-2026"]
    ga = average.RaceAverage(race_id=gen.id, as_of=date(2026, 11, 3), values={"Democrats": 50.8, "Republicans": 42.8},
                             margin=8.0, latest_end_date=date(2026, 11, 2))
    assert build.seo_title(gen, ga, date(2026, 11, 2)) == "2026 Generic Ballot Polls Today: Democrats +8.0 (Nov 2, 2026)"
    assert build.seo_title(gen, ga, date(2026, 11, 4)) == "Final 2026 Generic Ballot Average: Democrats +8.0 (Nov 3, 2026)"
    assert build.seo_title(gen, ga, date(2026, 12, 20), certified=True) == "Final 2026 Generic Ballot Average: Democrats +8.0 vs. the Result"


def test_home_title_follows_the_midterm_calendar():
    from datetime import date
    assert build.home_head(date(2026, 11, 3), False)["title"] == "2026 Midterm Polls vs. Results, 2028 Odds"
    assert build.home_head(date(2026, 11, 6), True)["title"] == "Did the Polls Get the 2026 Midterms Right?"
    assert build.home_head(date(2027, 3, 1), False)["h1"] == "How is 2028 looking?"
    assert all(len(build.home_head(d, r)["title"] + " | ElectionsUSA") <= 60 for d in (date(2026, 11, 3), date(2027, 1, 1)) for r in (True, False))


def test_scorecard_claims_and_typical_error_are_consistent(site):
    import re
    sc = (site / "pollsters" / "index.html").read_text()
    assert "first independent pollster rating" not in sc
    typical = re.search(r"missed by (\d+\.\d) points on average", sc).group(1)
    yougov = (site / "pollsters" / "yougov" / "index.html").read_text()
    assert f"all pollsters {typical}" in yougov
    home = (site / "index.html").read_text()
    assert "<th class=\"num\">Adjusted</th>" in home  # the column the table is sorted by is visible


def test_calendar_leads_with_the_dnc_date_and_marks_gop_tentative(site):
    html = (site / "2028" / "calendar" / "index.html").read_text()
    assert "South Carolina holds the first 2028 Democratic primary on January 22, 2028" in html
    assert "traditionally lead" not in html
    from pipeline import config
    gop = [r for r in config.PRIMARY_CALENDAR_2028 if "Republican" in r[1]]
    assert gop and all(r[4] == "tentative" for r in gop)
    assert all(r[3] for r in config.PRIMARY_CALENDAR_2028 if "Democratic primary" in r[1])  # every DNC date is sourced


def test_pollster_pages_carry_webpage_dataset_and_faq(site):
    import json, re
    html = (site / "pollsters" / "yougov" / "index.html").read_text()
    types = [json.loads(b).get("@type") for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    assert {"WebPage", "Dataset", "FAQPage"} <= set(types)
    assert "Is YouGov accurate?" in html and "Does YouGov lean Democratic or Republican?" in html


def test_long_tables_cap_at_50_with_faq_first(site):
    html = (site / "2026" / "generic-ballot" / "index.html").read_text()
    table = html[html.index('<table class="table polls">'):]
    assert table.count("<tr") - 1 == build.MAX_TABLE_ROWS  # header row excluded
    assert "Latest 50 polls" in html and "/data/polls.csv" in html
    assert html.index('id="faq"') < html.index('id="all-polls"')


def test_thin_matchup_is_flagged_and_noindexed(site):
    html = (site / "2028" / "president" / "vance-vs-buttigieg" / "index.html").read_text()
    assert '<meta name="robots" content="noindex, follow">' in html and "Limited data." in html
    assert "max-image-preview" not in html
    assert "/2028/president/vance-vs-buttigieg/</loc>" not in (site / "sitemap.xml").read_text()


def test_title_and_description_lengths(site):
    import html as h, re
    long_titles = []
    for p in site.rglob("index.html"):
        s = p.read_text()
        t = h.unescape(re.search(r"<title>([^<]*)", s).group(1))
        d = h.unescape(re.search(r'<meta name="description" content="([^"]*)', s).group(1))
        assert len(d) <= build.DESCRIPTION_MAX, (p, d)
        if len(t) > build.TITLE_MAX:
            long_titles.append(t)
        if " | ElectionsUSA" in t:
            assert len(t) <= build.TITLE_MAX, t
    # only pages whose own subject name is long run past 60 characters
    assert all(len(t) <= 70 or t.startswith("Is ") for t in long_titles), long_titles
    assert build.clip("One. Two words here that run on " * 10).endswith((".", "…"))


def test_pollster_pages_have_their_own_share_card(site):
    html = (site / "pollsters" / "yougov" / "index.html").read_text()
    assert "/og/pollsters/yougov.png" in html and (site / "og" / "pollsters" / "yougov.png").exists()


def test_geo_leads_and_machine_files(election_day_site):
    import json, re
    sc = (election_day_site / "pollsters" / "index.html").read_text()
    assert "the top-rated U.S. pollster is" in sc and "adjusted error of" in sc
    types = [json.loads(b).get("@type") for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', sc, re.S)]
    assert "Dataset" in types
    llms = (election_day_site / "llms.txt").read_text()
    for path in ("/about/", "/2026/pollster-accuracy/", "/markets/", "/sitemap.xml", "/feed.xml"):
        assert f"https://electionsusa.org{path}" in llms, path
    gb = (election_day_site / "2026" / "generic-ballot" / "index.html").read_text()
    assert "vs. the Result" not in re.search(r"<title>([^<]*)", gb).group(1)
    assert "<h4" not in gb


def test_home_lead_has_the_final_number():
    from datetime import date
    head = build.home_head(date(2026, 11, 4), False, final="Democrats +8.0 (119 polls)")
    assert head["sub"].startswith("The final generic ballot average had Democrats +8.0 (119 polls).")


ISO_DATE = r"\d{4}(-\d{2}(-\d{2})?)?"


def check_dataset(ds: dict) -> list[str]:
    """Problems Google's Dataset rich-result rules would flag on one JSON-LD block."""
    bad = []
    if not isinstance(ds.get("name"), str) or not ds["name"]:
        bad.append("name")
    if not isinstance(ds.get("description"), str) or not 50 <= len(ds["description"]) <= 5000:
        bad.append("description")
    if not str(ds.get("url", "")).startswith("https://"):
        bad.append("url")
    creators = ds.get("creator") if isinstance(ds.get("creator"), list) else [ds.get("creator")]
    if not all(isinstance(c, dict) and c.get("@type") in ("Organization", "Person") and c.get("name") for c in creators):
        bad.append("creator")
    if not str(ds.get("license", "")).startswith("https://"):
        bad.append("license")
    tc = ds.get("temporalCoverage")
    if tc is not None and not re.fullmatch(f"{ISO_DATE}(/({ISO_DATE}|\\.\\.))?", str(tc)):
        bad.append("temporalCoverage")
    sc = ds.get("spatialCoverage")
    if not (isinstance(sc, str) or (isinstance(sc, dict) and sc.get("@type") == "Place" and (sc.get("name") or sc.get("geo")))):
        bad.append("spatialCoverage")
    dist = ds.get("distribution", [])
    if not dist or not all(d.get("@type") == "DataDownload" and d.get("encodingFormat") and str(d.get("contentUrl", "")).startswith("https://")
                           for d in dist):
        bad.append("distribution")
    return bad


def test_every_dataset_block_is_valid_for_google(site):
    seen = {}
    for page in site.rglob("index.html"):
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page.read_text(), re.S):
            ld = json.loads(block)
            for node in ld.get("@graph", [ld]) if isinstance(ld, dict) else ld:
                if node.get("@type") == "Dataset":
                    seen[str(page.relative_to(site))] = node
    assert len(seen) > 50
    problems = {path: bad for path, node in seen.items() if (bad := check_dataset(node))}
    assert not problems, problems
    # one national race, one state and one single-election page, spelled out
    assert seen["approval/trump/index.html"]["spatialCoverage"] == {"@type": "Place", "name": "United States"}
    assert seen["states/pennsylvania/index.html"]["spatialCoverage"] == {"@type": "Place", "name": "Pennsylvania, United States"}
    assert seen["states/pennsylvania/index.html"]["temporalCoverage"] == "1976/2024"
    assert '"Country"' not in json.dumps(list(seen.values()))
