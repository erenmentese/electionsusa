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


def test_adsense_script_alone_until_ad_units_exist():
    html = render("privacy.html", adsense_client="ca-pub-1")
    assert html.count("adsbygoogle.js?client=ca-pub-1") == 1  # what AdSense looks for when it verifies the site
    env = Environment(loader=FileSystemLoader(str(config.TEMPLATE_DIR)), trim_blocks=True, lstrip_blocks=True)
    slot = env.from_string('{% from "_macros.html" import ad %}{{ ad("home-top") }}')
    assert slot.render(site={**config.SITE, "adsense_client": "ca-pub-1"}).strip() == ""  # no unit yet, no empty box
    assert slot.render(site={**config.SITE, "ad_slots": {"home-top": "123"}}).strip() == ""  # no AdSense, no ad
    html = slot.render(site={**config.SITE, "adsense_client": "ca-pub-1", "ad_slots": {"home-top": "123"}})
    assert 'data-ad-client="ca-pub-1" data-ad-slot="123"' in html and 'aria-label="Advertisement"' in html


def test_no_ga4_tag_when_unset():
    html = render("privacy.html", ga4_id="")
    assert "googletagmanager" not in html
    assert "gtag(" not in html
    assert "Google Analytics" not in html


def test_homepage_photos_are_labelled_lazy_and_sized(site):
    html = (site / "index.html").read_text()
    for img in ("reading-polls.jpg", "talking-politics.jpg"):
        tag = html[html.index(f'src="/static/img/{img}"'):]
        tag = tag[:tag.index(">")]
        assert 'width="1200" height="904"' in tag and 'loading="lazy"' in tag and 'alt="' in tag
        assert (site / "static" / "img" / img).stat().st_size < 300_000
    assert html.count("AI-generated image, not a photograph of real people.") == 2
