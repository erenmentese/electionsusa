import dataclasses
import json
import re
from datetime import date

import pandas as pd
import pytest

from pipeline import accuracy, build, config
from pipeline.schema import validate_polls


def polls(*rows):
    out = []
    for pid, firm, end, dem, rep in rows:
        base = dict(poll_id=pid, race_id="generic-ballot-2026", pollster=firm, sponsor="", start_date=end, end_date=end,
                    sample_size=1000, population="LV", source_url="", source_type="wikipedia", notes="", fetched_at="")
        out += [base | dict(candidate="Democrats", pct=dem), base | dict(candidate="Republicans", pct=rep)]
    return validate_polls(pd.DataFrame(out))


def test_scoring_ranks_by_error_and_labels_bias():
    df = polls(("a", "Ipsos", "2026-11-01", 51, 44), ("b", "Ipsos", "2026-10-25", 50, 45), ("c", "YouGov", "2026-10-30", 52, 42),
               ("old", "YouGov", "2026-09-01", 60, 30))  # outside the final three weeks
    final = accuracy.final_polls(df)
    assert {p["poll_id"] for p in final} == {"a", "b", "c"}
    pending = accuracy.score(final, None)
    assert all(r["error"] is None for r in pending) and "still being counted" in accuracy.answer(pending, None, 8.0)
    result = accuracy.Result(dem_pct=50.0, rep_pct=45.0, status="preliminary", counted_pct=90, as_of=date(2026, 11, 5),
                             source="Test count", source_url="https://example.org")
    rows = accuracy.score(final, result)
    assert [r["pollster"] for r in rows] == ["Ipsos", "YouGov"]
    assert rows[0]["error"] == 1.0 and accuracy.bias_label(rows[1]["bias"]) == "D+5.0"
    text = accuracy.answer(rows, result, 8.0, min_polls=1)
    assert "Ipsos is the closest generic-ballot pollster of 2026 so far" in text and "most accurate" not in text
    assert "90% of the expected vote counted" in text and "D+8.0 against a count so far of D+5.0" in text
    # an early count names nobody; only a certified result has a "most accurate" pollster
    early = accuracy.answer(rows, dataclasses.replace(result, counted_pct=60), 8.0, min_polls=1)
    assert "Ipsos" not in early and "ranked once most of the vote is counted" in early
    final = accuracy.answer(rows, dataclasses.replace(result, status="certified"), 8.0, min_polls=1)
    assert final.startswith("Ipsos was the most accurate generic-ballot pollster of 2026 on the certified House popular vote")


def test_pending_accuracy_page_and_first_article(election_day_site):
    page = (election_day_site / "2026" / "pollster-accuracy" / "index.html").read_text()
    assert "pending" in page and "Which Pollster Was Most Accurate in 2026?" in page
    assert not re.search(r'<td class="num">\d+\.\d</td><td class="num">[DR]\+', page)  # no error figures before a result
    assert (election_day_site / "data" / "2026-generic-ballot-accuracy.csv").exists()
    art = (election_day_site / "analysis" / "final-generic-ballot-2026" / "index.html").read_text()
    ld = next(json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', art, re.S) if '"Article"' in b)
    assert ld["datePublished"] == "2026-11-03" and ld["image"]["width"] == 1200 and ld["author"]["@type"] in ("Person", "Organization")
    assert '<meta name="robots" content="max-image-preview:large">' in art and 'og:type" content="article"' in art
    assert not (election_day_site / "analysis" / "polls-vs-results-2026-house-popular-vote").exists()  # needs a result
    assert "/analysis/final-generic-ballot-2026/" in (election_day_site / "analysis" / "index.html").read_text()


def test_result_file_turns_on_scores_and_second_article(tmp_path, monkeypatch):
    res = tmp_path / "2026-house-national.json"
    res.write_text(json.dumps(dict(dem_pct=51.0, rep_pct=45.5, status="preliminary", counted_pct=88, as_of="2026-11-05",
                                   source="Test count", source_url="https://example.org/count")))
    monkeypatch.setattr(accuracy, "RESULT_PATH", res)
    monkeypatch.setattr(accuracy.load_result, "__defaults__", (res,))
    monkeypatch.setattr(config, "DIST_DIR", tmp_path / "dist")
    dist = build.build(date(2026, 11, 5))
    page = (dist / "2026" / "pollster-accuracy" / "index.html").read_text()
    assert "preliminary" in page and "closest generic-ballot pollster of 2026 so far" in page and "Test count" in page
    assert (dist / "analysis" / "polls-vs-results-2026-house-popular-vote" / "index.html").exists()
    csv = pd.read_csv(dist / "data" / "2026-generic-ballot-accuracy.csv")
    assert csv["error"].notna().all() and set(csv["result_status"]) == {"preliminary"}


def write_result(tmp_path, monkeypatch, **fields):
    res = tmp_path / "2026-house-national.json"
    res.write_text(json.dumps(fields))
    monkeypatch.setattr(accuracy, "RESULT_PATH", res)
    monkeypatch.setattr(accuracy.load_result, "__defaults__", (res,))
    return res


COUNT = dict(dem_pct=51.4, rep_pct=46.2, status="preliminary", counted_pct=86, as_of="2026-11-05T15:00Z",
             source="Test count", source_url="https://example.org/count",
             history=[dict(dem_pct=52.0, rep_pct=45.9, counted_pct=78, as_of="2026-11-04T16:00Z",
                           source="Earlier count", source_url="https://example.org/early")])


def test_result_file_is_validated_and_timestamped(tmp_path, monkeypatch):
    res = write_result(tmp_path, monkeypatch, **COUNT)
    r = accuracy.load_result(res)
    assert r.margin == 5.2 and r.iso == "2026-11-05T15:00Z" and r.stamp == "November 5, 2026, 10 a.m. ET"
    assert [h.source for h in r.history] == ["Earlier count"] and r.nameable
    assert accuracy.known_on(r, date(2026, 11, 4)) is None and accuracy.known_on(r, date(2026, 11, 5)) is r
    for bad, message in [(dict(COUNT, dem_pct=60, rep_pct=45), "shares of all House votes"),
                         (dict(COUNT, status="final"), "status"),
                         (dict(COUNT, source_url="example.org"), "https://"),
                         (dict(COUNT, as_of="Nov 5"), "as_of"),
                         (dict(COUNT, history=[dict(COUNT["history"][0], as_of="2026-11-06T10:00Z")]), "older than the current count"),
                         (dict(COUNT, history=[dict(COUNT["history"][0], as_of="2026-11-04T18:00Z"), COUNT["history"][0]]), "oldest first")]:
        res.write_text(json.dumps(bad))
        with pytest.raises(ValueError, match=message):
            accuracy.load_result(res)


def test_every_2026_page_shows_the_same_labelled_count(tmp_path, monkeypatch):
    write_result(tmp_path, monkeypatch, **COUNT)
    monkeypatch.setattr(config, "DIST_DIR", tmp_path / "dist")
    dist = build.build(date(2026, 11, 5))
    race = (dist / "2026" / "generic-ballot" / "index.html").read_text()
    block = race.split('id="vs-result"')[1].split("</section>")[0]
    assert "(preliminary)" in block and "pending" not in block and "51.4%" in block and "46.2%" in block and "D +5.2" in block
    assert "Unofficial count with about 86% of the expected vote counted" in block and 'datetime="2026-11-05T15:00Z"' in block
    hub = (dist / "2026" / "index.html").read_text()
    assert "Democrats 51.4%, Republicans 46.2% (D+5.2)" in hub and "We don't call races" in hub
    acc = (dist / "2026" / "pollster-accuracy" / "index.html").read_text()
    assert "<title>2026 Pollster Accuracy vs. the Preliminary House Vote" in acc
    assert "How the count moved" in acc and "Earlier count" in acc and "78%" in acc
    sc = (dist / "pollsters" / "index.html").read_text().split('id="2026"')[1].split("</section>")[0]
    assert "preliminary national House popular vote, with about 86% of the expected vote counted" in sc
    assert sc.count("<tr>") > 5 and "+5.2" in sc
    # a preliminary count never shows up as a headline number or a "most accurate" claim in titles
    for page in dist.rglob("index.html"):
        title = re.search(r"<title>([^<]*)", page.read_text()).group(1)
        assert "5.2" not in title and "Most Accurate 2026 Pollsters" not in title, (page, title)
    sitemap = (dist / "sitemap.xml").read_text()
    for path in ("/2026/generic-ballot/", "/2026/", "/pollsters/"):
        assert f"<loc>https://electionsusa.org{path}</loc><lastmod>2026-11-05</lastmod>" in sitemap, path
    # a partial count is never the "actual" result, and nobody "called" the popular vote on it
    assert "Count so far" in sc and "pending" in sc and "✓" not in sc and "✗" not in sc
    pollster = next(p.read_text() for p in (dist / "pollsters").glob("*/index.html") if 'id="2026"' in p.read_text())
    assert "Count so far" in pollster and "unofficial count so far" in pollster and "✓" not in pollster.split('id="2026"')[1].split("</section>")[0]
    # descriptions keep the ET time whole, the article dek says how much is counted, the CSV says which count it used
    desc = re.search(r'<meta name="description" content="([^"]*)', acc).group(1)
    assert "10 a.m. ET)" in desc
    art = (dist / "analysis" / "polls-vs-results-2026-house-popular-vote" / "index.html").read_text()
    assert "The preliminary House popular vote is D+5.2, with about 86% of the expected vote counted" in art
    assert '"datePublished": "2026-11-04"' in art and "The count so far" in art
    csv = pd.read_csv(dist / "data" / "2026-generic-ballot-accuracy.csv")
    assert set(csv["result_as_of"]) == {"2026-11-05T15:00Z"} and set(csv["result_counted_pct"]) == {86}
    home = (dist / "index.html").read_text()
    assert "unofficial House count so far" in home and "certified House result" not in home
    assert "votes are being counted" in hub
    llms = (dist / "llms.txt").read_text()
    assert "generic-ballot/): " in llms and "(latest poll 2026-11-02)" in llms.split("generic-ballot/): ")[1].split("\n")[0]


def test_early_count_names_and_ranks_no_pollster(tmp_path, monkeypatch):
    write_result(tmp_path, monkeypatch, **dict(COUNT, counted_pct=60, history=[]))
    monkeypatch.setattr(config, "DIST_DIR", tmp_path / "dist")
    dist = build.build(date(2026, 11, 5))
    acc = (dist / "2026" / "pollster-accuracy" / "index.html").read_text()
    assert "Pollsters are ranked once most of the vote is counted" in acc
    counts = [int(n) for n in re.findall(r'<td class="muted"></td><td>.*?</td><td class="num">(\d+)</td>', acc)]
    assert counts and counts == sorted(counts, reverse=True)  # by number of polls, not by error
    art = (dist / "analysis" / "polls-vs-results-2026-house-popular-vote" / "index.html").read_text()
    assert "Closest pollsters" not in art and "those with the most polls" in art


def test_pending_titles_claim_no_result(election_day_site):
    acc = (election_day_site / "2026" / "pollster-accuracy" / "index.html").read_text()
    assert "<title>2026 Pollster Accuracy: House Vote Count Pending" in acc


def test_election_day_race_page_says_pending(election_day_site):
    block = (election_day_site / "2026" / "generic-ballot" / "index.html").read_text().split('id="vs-result"')[1].split("</section>")[0]
    assert "(pending)" in block and "still being counted" in block
