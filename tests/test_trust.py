import json
import re

from pipeline import build, config


def ld_blocks(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def test_adsense_live_without_empty_ad_boxes(site):
    pub = config.SITE["adsense_client"]
    assert re.fullmatch(r"ca-pub-\d{16}", pub)
    assert (site / "ads.txt").read_text().strip() == f"google.com, {pub.removeprefix('ca-')}, DIRECT, f08c47fec0942fa0"
    pages = list(site.rglob("index.html"))
    assert pages and all(f"adsbygoogle.js?client={pub}" in p.read_text() for p in pages)  # AdSense verifies any page
    if not config.SITE["ad_slots"]:  # no ad units yet: script only, no empty boxes
        assert not [p for p in pages if "ad-placeholder" in p.read_text() or 'class="ad"' in p.read_text()]
    privacy = (site / "privacy" / "index.html").read_text()
    assert "We use Google AdSense" in privacy and "shows no advertising" not in privacy
    assert "funded by display advertising" in (site / "about" / "index.html").read_text()


def test_corrections_and_terms_pages(site):
    corr = (site / "corrections" / "index.html").read_text()
    assert "Democrats +8.1, from 152 polls" in corr and "/2026/generic-ballot/" in corr
    assert (site / "data" / "corrections.csv").exists()
    terms = (site / "terms" / "index.html").read_text()
    assert "CC BY 4.0" in terms and "investment" in terms
    sitemap = (site / "sitemap.xml").read_text()
    assert "/corrections/</loc>" in sitemap and "/terms/</loc>" in sitemap


def test_organization_schema_and_report_link(site):
    about = (site / "about" / "index.html").read_text()
    org = next(n for b in ld_blocks(about) for n in b.get("@graph", []) if n["@type"] == "Organization")
    assert org["alternateName"] == "ElectionsUSA.org"
    assert org["publishingPrinciples"].endswith("/methodology/") and org["correctionsPolicy"].endswith("/corrections/")
    assert org["foundingDate"] == "2026-10"
    assert org["founder"]["name"] == "Eren Menteşe" and "https://www.linkedin.com/in/ernmentese/" in org["founder"]["sameAs"]
    assert "Eren Menteşe" in about and 'rel="me noopener"' in about
    assert "github.com/erenmentese/electionsusa/issues/new" in about and "Report a data error".lower() in about.lower()


def test_named_editor_becomes_founder(monkeypatch):
    monkeypatch.setitem(config.SITE, "editor", {"name": "Jane Doe", "role": "Founder and editor", "bio": "", "same_as": ["https://x.com/jane"]})
    org = next(n for n in build.site_ld()["@graph"] if n["@type"] == "Organization")
    assert org["founder"]["@type"] == "Person" and org["founder"]["sameAs"] == ["https://x.com/jane"]


def test_license_is_split_by_source(site):
    data = (site / "data" / "index.html").read_text()
    assert "CC BY-SA 4.0" in data and "subject to the terms of the platform" in data
    ds = next(b for b in ld_blocks(data) if b.get("@type") == "Dataset")
    assert ds["license"] == "https://creativecommons.org/licenses/by-sa/4.0/"
    race = next(b for b in ld_blocks((site / "approval" / "trump" / "index.html").read_text()) if b.get("@type") == "Dataset")
    assert race["license"].endswith("/by/4.0/") and race["creator"]["@id"].endswith("/#org")
