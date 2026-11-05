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
    assert re.fullmatch(host["has"][0]["value"], "electionsusa.vercel.app") and host["destination"] == "https://electionsusa.org/$1"
    assert host["permanent"] is True  # 308
    page = (site / "404.html").read_text()
    assert '<meta name="robots" content="noindex">' in page and "max-image-preview" not in page
    assert '<meta name="robots" content="max-image-preview:large">' in (site / "index.html").read_text()


def test_cloudflare_pages_headers_and_redirects_match_vercel(site):
    v = json.loads((config.ROOT / "vercel.json").read_text())
    headers = (site / "_headers").read_text()
    sitewide = headers.split("\n\n")[0].splitlines()
    assert sitewide[0] == "/*"
    assert {tuple(line.strip().split(": ", 1)) for line in sitewide[1:]} == {
        (h["key"], h["value"]) for h in v["headers"][0]["headers"]}
    assert "/404.html\n  X-Robots-Tag: noindex" in headers
    assert "https://:project.pages.dev/*\n  X-Robots-Tag: noindex" in headers  # no duplicate of the site in search
    rules = {tuple(line.split()) for line in (site / "_redirects").read_text().splitlines()}
    assert {(r["source"], r["destination"], str(r["statusCode"])) for r in v["redirects"] if "statusCode" in r} == rules
    workflow = (config.ROOT / ".github" / "workflows" / "update-and-deploy.yml").read_text()
    assert "sh build.sh" in workflow and "pages deploy dist --project-name=electionsusa" in workflow
    assert workflow.index("Run tests") < workflow.index("Deploy to Cloudflare Pages")  # only tested builds go live


def test_one_nav_on_every_page_with_more_menu_and_mobile_search(site):
    def links(html):
        head = re.search(r'<header class="site-header">(.*?)</header>', html, re.S).group(1)
        return re.findall(r'<a href="(/[^"]*)"', head)
    home = links((site / "index.html").read_text())
    inner_html = (site / "markets" / "index.html").read_text()
    assert home == links(inner_html)
    assert "/pollsters/" in home and "/data/" in home and "/markets/" in home
    assert "data-search-toggle" in inner_html  # phones get a search icon on inner pages


def test_indexnow_key_file_and_changed_urls(site):
    from pipeline import indexnow
    assert (site / f"{config.INDEXNOW_KEY}.txt").read_text() == config.INDEXNOW_KEY
    old = "<url><loc>https://e.org/a/</loc><lastmod>2026-11-01</lastmod></url><url><loc>https://e.org/b/</loc><lastmod>2026-11-01</lastmod></url>"
    new = "<url><loc>https://e.org/a/</loc><lastmod>2026-11-01</lastmod></url><url><loc>https://e.org/b/</loc><lastmod>2026-11-03</lastmod></url><url><loc>https://e.org/c/</loc></url>"
    assert indexnow.changed(new, old) == ["https://e.org/b/", "https://e.org/c/"]


def test_llms_txt_feed_and_api_table(site):
    import xml.etree.ElementTree as ET
    llms = (site / "llms.txt").read_text()
    assert "## Current averages" in llms and "/api/approval-trump-2.json" in llms and "CC BY-SA 4.0" in llms and "Cite as" in llms
    feed = ET.fromstring((site / "feed.xml").read_text())
    ns = {"a": "http://www.w3.org/2005/Atom"}
    assert len(feed.findall("a:entry", ns)) >= 5
    assert 'type="application/atom+xml"' in (site / "index.html").read_text()
    data = (site / "data" / "index.html").read_text()
    assert "/api/search-index.json" in data and "/llms.txt" in data


def test_icons_manifest_contrast_and_countdown_schema(site):
    import re
    assert (site / "favicon.ico").exists() and (site / "static" / "img" / "apple-touch-icon.png").exists()
    assert json.loads((site / "site.webmanifest").read_text())["icons"]
    css = (config.STATIC_DIR / "css" / "style.css").read_text()

    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    mute, paper = re.search(r"--mute:(#[0-9a-f]{6})", css).group(1), re.search(r"--paper:(#[0-9a-f]{6})", css).group(1)
    assert (lum(paper) + 0.05) / (lum(mute) + 0.05) >= 4.5  # WCAG AA for small text
    countdown = (site / "countdown" / "index.html").read_text()
    assert '"@type":"Event"' not in countdown and '"@type":"WebPage"' in countdown
