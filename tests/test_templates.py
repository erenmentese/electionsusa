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


def test_newsletter_signup_only_once_a_form_is_configured():
    html = render("privacy.html", newsletter_form_id="")
    assert "app.kit.com" not in html and 'id="newsletter"' not in html
    html = render("privacy.html", newsletter_form_id="1234567")
    assert 'action="https://app.kit.com/forms/1234567/subscriptions" method="post"' in html
    assert 'name="email_address"' in html and 'type="email"' in html and "required" in html
    assert '<label for="nl-email"' in html
    # the policy names the processor wherever the form can appear
    assert 'id="newsletter"' in html and "Kit (ConvertKit)" in html


def test_lead_illustrations_are_labelled_and_sized(site):
    for page, img in (("methodology", "polls-to-average.jpg"), ("pollsters", "pollster-accuracy.jpg")):
        html = (site / page / "index.html").read_text()
        assert f'src="/static/img/{img}" width="1200" height="800" alt="Illustration:' in html
        assert "Illustration generated with AI" in html
        assert (site / "static" / "img" / img).stat().st_size < 300_000
