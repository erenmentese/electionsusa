import io
from datetime import date, datetime, timezone

import pandas as pd
import pytest
from PIL import Image

from pipeline import config, social_compose as sc
from pipeline.schema import make_poll_id
from pipeline.seed_data import seed_polls_frame
from pipeline.social_cards import render
from pipeline.social_text import fit_lines, weighted_length
from pipeline.xclient import XClient

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
TODAY = NOW.date()  # a Thursday, 5 days before the midterms: no roundup, no milestone


def add_poll(polls, race_id="dem-primary-2028", end="2026-10-25", vals=None, pollster="Test Pollster"):
    vals = vals or {"Kamala Harris": 24.0, "Gavin Newsom": 22.0, "Pete Buttigieg": 15.0}
    pid = make_poll_id(race_id, pollster, end, "LV")
    rows = [dict(poll_id=pid, race_id=race_id, pollster=pollster, sponsor="", start_date="2026-10-22", end_date=end,
                 sample_size=1000, population="LV", candidate=c, pct=v, source_url="https://example.com",
                 source_type="manual", notes="", fetched_at="") for c, v in vals.items()]
    return pd.concat([polls, pd.DataFrame(rows)], ignore_index=True), pid


def test_weighted_length_counts_urls_and_emoji():
    assert weighted_length("hello") == 5
    assert weighted_length("see https://electionsusa.org/2028/democratic-primary/ now") == 4 + 23 + 4
    assert weighted_length("📊") == 2
    long = ["x" * 200, "y" * 200]
    assert weighted_length(fit_lines(long, optional_from=1)) <= 280


def test_bootstrap_then_only_new_polls_are_planned():
    polls = seed_polls_frame()
    state = sc.empty_state()
    assert sc.bootstrap(polls, state, NOW) == polls["poll_id"].nunique()
    assert sc.plan(polls, None, state, TODAY, NOW) == []
    polls2, pid = add_poll(polls)
    planned = sc.plan(polls2, None, state, TODAY, NOW)
    assert [p.key for p in planned] == [f"poll:{pid}"]
    text = planned[0].text
    assert "2028 Democratic primary" in text and "Harris 24%" in text and "1,000 likely voters" in text
    assert weighted_length(text) <= 280
    assert "http" not in text  # links are off by default (X charges more for link posts)


def test_stale_polls_and_daily_cap():
    polls = seed_polls_frame()
    state = sc.empty_state()
    sc.bootstrap(polls, state, NOW)
    polls, old = add_poll(polls, end="2026-09-01", pollster="Old Poll")
    for i in range(4):
        polls, _ = add_poll(polls, end="2026-10-26", pollster=f"Fresh {i}")
    planned = sc.plan(polls, None, state, TODAY, NOW)
    assert f"poll:{old}" not in [p.key for p in planned]
    assert len(planned) == config.BOT["max_posts_per_run"]
    state["log"] = [{"ts": NOW.isoformat(), "key": f"k{i}", "live": True} for i in range(config.BOT["max_posts_per_day"])]
    assert sc.plan(polls, None, state, TODAY, NOW) == []


def test_milestones_and_roundup():
    d = date(2026, 10, 27)  # 7 days before the midterms
    keys = [p.key for p in sc.milestone_posts(d)]
    assert "milestone:2026:7" in keys
    monday = date(2026, 10, 26)
    rp = sc.roundup_post(sc.validate_polls(seed_polls_frame()), None, monday)
    assert rp and rp.key == "roundup:2026-10-26" and "Trump approval" in rp.text


def test_card_renders_png():
    polls = sc.validate_polls(seed_polls_frame())
    pid = polls[polls.race_id == "pres-2028-vance-newsom"].sort_values("end_date")["poll_id"].iat[-1]
    post = sc.poll_post(pid, polls, None, TODAY)
    img = Image.open(io.BytesIO(render(post.card)))
    assert img.size == (1600, 900)
    assert post.alt.startswith("Zogby Analytics")


class FakeResp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.headers = status, payload, {}
        self.content = b"x"
        self.text = str(payload)

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, upload_status=200):
        self.calls, self.upload_status = [], upload_status

    def post(self, url, **kw):
        self.calls.append((url, kw))
        if "media/upload" in url:
            return FakeResp(self.upload_status, {"media_id_string": "123"})
        if "metadata" in url:
            return FakeResp(200, {})
        return FakeResp(201, {"data": {"id": "999", "text": kw["json"]["text"]}})


@pytest.fixture
def creds(monkeypatch):
    for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"):
        monkeypatch.setenv(k, "test")


def test_client_posts_with_media(creds):
    s = FakeSession()
    assert XClient(session=s).post_with_card("hi", b"png", "alt") == "999"
    post = [c for c in s.calls if c[0].endswith("/2/tweets")][0]
    assert post[1]["json"] == {"text": "hi", "media": {"media_ids": ["123"]}}


def test_client_falls_back_to_text_when_upload_fails(creds):
    s = FakeSession(upload_status=403)
    assert XClient(session=s).post_with_card("hi", b"png") == "999"
    post = [c for c in s.calls if c[0].endswith("/2/tweets")][0]
    assert post[1]["json"] == {"text": "hi"}
