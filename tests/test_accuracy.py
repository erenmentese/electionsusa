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
    assert text.startswith("Ipsos was the most accurate generic-ballot pollster of 2026 on the preliminary House popular vote")
    assert "90% of the expected vote counted" in text and "D+8.0 against a result of D+5.0" in text


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
    assert "preliminary" in page and "most accurate generic-ballot pollster of 2026" in page and "Test count" in page
    assert (dist / "analysis" / "polls-vs-results-2026-house-popular-vote" / "index.html").exists()
    csv = pd.read_csv(dist / "data" / "2026-generic-ballot-accuracy.csv")
    assert csv["error"].notna().all() and set(csv["result_status"]) == {"preliminary"}
