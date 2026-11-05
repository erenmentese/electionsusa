from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline import config


def render(template, **site_overrides):
    env = Environment(loader=FileSystemLoader(str(config.TEMPLATE_DIR)), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    site = {**config.SITE, **site_overrides}
    return env.get_template(template).render(site=site, nav=[], races=[], path="/privacy/", build_date="today", year=2026)


def test_ga4_tag_with_consent_defaults():
    html = render("privacy.html", ga4_id="G-TEST123")
    assert html.count("googletagmanager.com/gtag/js") == 1
    assert 'gtag("config", "G-TEST123")' in html
    assert 'location.hostname === "electionsusa.org"' in html
    # region-restricted "denied" default must come before the tag loads
    head = html[:html.index("googletagmanager.com/gtag/js")]
    assert '"denied"' in head and '"DE"' in head and '"GB"' in head and '"RE"' in head
    # no AdSense yet, so ad cookies are denied everywhere
    assert 'ad_storage: "granted"' not in head
    assert "Google Analytics 4" in html
    assert "do not collect names" not in html


def test_ad_consent_follows_adsense():
    html = render("privacy.html", ga4_id="G-TEST123", adsense_client="ca-pub-1")
    assert 'ad_storage: "granted", ad_user_data: "granted", ad_personalization: "granted", analytics_storage: "granted"' in html
    assert "do not use Google Analytics data for advertising" not in html


def test_no_ga4_tag_when_unset():
    html = render("privacy.html", ga4_id="")
    assert "googletagmanager" not in html
    assert "gtag(" not in html
    assert "Google Analytics" not in html
