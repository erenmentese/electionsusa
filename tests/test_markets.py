import json

import pandas as pd

from pipeline import build, check_data, fetch_markets


class FakeSession:
    def __init__(self, markets):
        self.markets = markets

    def get(self, *a, **k):
        payload = [{"markets": self.markets}]

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return payload
        return R()


def market(label, yes, **kw):
    return {"groupItemTitle": label, "outcomes": json.dumps(["Yes", "No"]), "outcomePrices": json.dumps([str(yes), str(1 - yes)]),
            "active": True, "closed": False, "volumeNum": 2_000_000} | kw


def test_polymarket_skips_dead_contracts_and_normalises_names():
    rows = fetch_markets.polymarket_event("x", FakeSession([
        market("J.D. Vance", 0.364),
        market("Robert F. Kennedy Jr.", 0.49, closed=True),
        market("Nikki Haley", 0.03, active=False),
        market("Someone", 0.2, volumeNum=500),
    ]))
    assert [r[0] for r in rows] == ["JD Vance"]
    assert fetch_markets.canonical_outcome("J.B. Pritzker") == "JB Pritzker"


def snap(day, outcome, price, platform="polymarket", source_type="api", notes=""):
    return dict(snapshot_date=f"2026-11-0{day}", market_id="gop-nominee-2028", platform=platform, outcome=outcome, price=price,
                source_url="", source_type=source_type, notes=notes, fetched_at="")


def test_markets_page_hides_frozen_prices_seed_rows_and_kalshi():
    rows = [snap(d, "Robert F. Kennedy Jr.", 49.0) for d in range(1, 5)]
    rows += [snap(d, "J.D. Vance", 35 + d) for d in range(1, 5)]
    rows += [snap(4, "JD Vance", 45.0, platform="kalshi", source_type="seed", notes="Press snapshot.")]
    ctx = {m["market"]["id"]: m for m in build.markets_context(pd.DataFrame(rows), {})}["gop-nominee-2028"]
    assert ctx["rows"] == [{"outcome": "JD Vance", "polymarket": 39.0}]
    assert ctx["hidden"] == ["Robert F. Kennedy Jr."]
    assert check_data.stale_prices(pd.DataFrame(rows)) == ["Robert F. Kennedy Jr."]


def test_built_markets_page_has_no_kalshi_column_or_internal_notes(site):
    html = (site / "markets" / "index.html").read_text()
    assert "<th class=\"num\">Kalshi</th>" not in html
    assert "Press snapshot" not in html and "possibly stale" not in html
    published = pd.read_csv(site / "data" / "markets.csv")
    assert set(published["platform"]) == {"polymarket"} and set(published["source_type"]) == {"api"}
