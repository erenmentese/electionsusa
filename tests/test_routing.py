import json
import re

from pipeline import config


def test_2028_hubs_exist_and_sit_in_breadcrumbs(site):
    hub = (site / "2028" / "index.html").read_text()
    pres = (site / "2028" / "president" / "index.html").read_text()
    assert 'href="/2028/president/vance-vs-newsom/"' in pres and 'href="/2028/democratic-primary/"' in hub
    race = (site / "2028" / "president" / "vance-vs-newsom" / "index.html").read_text()
    crumbs = next(json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', race, re.S) if "BreadcrumbList" in b)
    assert [i["item"].removeprefix(config.SITE["url"]) for i in crumbs["itemListElement"]] == [
        "/", "/2028/", "/2028/president/", "/2028/president/vance-vs-newsom/"]
    sitemap = (site / "sitemap.xml").read_text()
    assert "<loc>https://electionsusa.org/2028/</loc><lastmod>" in sitemap and "/2028/president/</loc><lastmod>" in sitemap


def test_vercel_redirects_and_404_noindex(site):
    v = json.loads((config.ROOT / "vercel.json").read_text())
    assert v["trailingSlash"] is True
    redirects = {(r["source"], r["destination"]): r for r in v["redirects"]}
    assert redirects[("/approval/", "/approval/trump/")]["statusCode"] == 301
    assert redirects[("/index.html", "/")]["statusCode"] == 301
    host = next(r for r in v["redirects"] if r.get("has"))
    assert host["has"][0]["value"] == "electionsusa.vercel.app" and host["destination"].startswith("https://electionsusa.org/")
    assert host["permanent"] is True  # 308
    page = (site / "404.html").read_text()
    assert '<meta name="robots" content="noindex">' in page and "max-image-preview" not in page
    assert '<meta name="robots" content="max-image-preview:large">' in (site / "index.html").read_text()
