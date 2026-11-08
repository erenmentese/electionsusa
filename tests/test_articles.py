import json
import re
from datetime import date

import pytest

from pipeline import articles, weekly
from pipeline.build import load_data


def test_every_written_article_parses_with_safe_inline_markup():
    pieces = [articles.parse(p) for p in sorted(articles.CONTENT_DIR.glob("*.md"))]
    assert len(pieces) >= 3
    for a in pieces:
        assert len(a["headline"]) <= 60 and len(a["dek"]) <= 155 and a["body"]  # titles and descriptions fit search results
    assert str(articles.inline("<b>x</b> & [poll](/approval/trump/)")) == '&lt;b&gt;x&lt;/b&gt; &amp; <a href="/approval/trump/">poll</a>'
    assert 'rel="nofollow noopener"' in articles.inline("[src](https://example.com/a)")
    with pytest.raises(ValueError):
        articles.inline("[src](http://example.com/a)")


def test_a_piece_stays_unpublished_before_its_date(site):
    assert not (site / "analysis" / "when-will-2028-presidential-candidates-announce").exists()


def test_written_analysis_is_published_bylined_and_linked(analysis_site):
    index = (analysis_site / "analysis" / "index.html").read_text()
    home = (analysis_site / "index.html").read_text()
    head = re.search(r'<header class="site-header">(.*?)</header>', home, re.S).group(1)
    assert 'href="/analysis/"' in head and "Latest analysis" in home
    for a in articles.load(date(2026, 11, 9)):
        page = (analysis_site / a["path"].strip("/") / "index.html").read_text()
        assert a["path"] in index
        assert '<a href="/about/#editor" rel="author">Eren Menteşe</a>' in page
        ld = [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
        art = next(x for x in ld if x.get("@type") == "Article")
        assert art["author"]["name"] == "Eren Menteşe" and art["datePublished"] == a["published"].isoformat()
        for href in re.findall(r'href="(/[^"#?]*)"', page):  # every internal link in the piece resolves
            target = analysis_site / href.strip("/")
            assert (target / "index.html").exists() or target.is_file(), (a["path"], href)


def test_weekly_numbers_cover_every_tracked_race():
    polls, _, ratings = load_data()
    rows = weekly.moves(polls, ratings, date(2026, 11, 8))
    assert [r["race"].id for r in rows] == list(weekly.RACES)
    md = weekly.markdown(polls, ratings, date(2026, 11, 8))
    assert "| Average | Now | A week earlier | Change |" in md and "| Poll | Ended | Race | Result |" in md
