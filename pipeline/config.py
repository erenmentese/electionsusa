"""Site- and race-level configuration for ElectionsUSA.

Everything that is likely to change between election cycles lives here:
race definitions, candidate names, Wikipedia source pages, prediction-market
slugs, dates and site metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
SITE_DIR = ROOT / "site"
TEMPLATE_DIR = SITE_DIR / "templates"
STATIC_DIR = SITE_DIR / "static"
DIST_DIR = ROOT / "dist"

SITE = {
    "name": "ElectionsUSA",
    "domain": "electionsusa.org",
    "url": "https://electionsusa.org",
    "tagline": "Open poll averages, pollster ratings and odds for U.S. elections",
    "description": (
        "Transparent, free polling averages for the 2028 presidential election, "
        "the Democratic and Republican primaries, presidential approval, "
        "pollster accuracy ratings and prediction-market odds. Open data, open methodology."
    ),
    "author": "ElectionsUSA Data Desk",  # byline used until `editor` is filled in
    # The named editor shown on About and as founder/author in structured data. Leave name empty to
    # keep the desk byline; nothing about a person is published until these are filled in.
    "editor": {
        "name": "Eren Menteşe",
        "role": "Founder and editor",
        "bio": ("Eren works in marketing communications in Istanbul, on brand strategy and campaign management, "
                "and built ElectionsUSA as an independent, personal project."),
        "same_as": ["https://www.linkedin.com/in/ernmentese/", "https://github.com/erenmentese"],
    },
    "founding_date": "2026-10",  # launched October 2026 (see About)
    "alternate_name": "ElectionsUSA.org",
    "issues_url": "https://github.com/erenmentese/electionsusa/issues/new",
    "terms_updated": "November 3, 2026",
    "contact_email": "ernmentesee@gmail.com",  # hello@electionsusa.org once forwarding is set up
    # Kit (kit.com, free up to 10,000 subscribers) form ID for the footer signup; empty = no signup form
    "newsletter_form_id": "",
    "twitter": "@ElectionsUSAorg",  # e.g. "@electionsusa"
    "github_repo": "erenmentese/electionsusa",  # e.g. "yourname/electionsusa" (enables data-download links)
    "adsense_client": "ca-pub-2827580140139884",  # empty = no AdSense script, no ads.txt
    # AdSense ad-unit IDs (numeric, from AdSense > Ads > By ad unit) by placement, e.g. {"home-top": "1234567890"}.
    # A placement without an ID renders nothing, so the site can go through AdSense review with only the script.
    "ad_slots": {},
    "analytics_snippet": "",  # paste a privacy-friendly analytics tag (Plausible, GoatCounter...)
    "ga4_id": "G-MN0XEQY44B",  # Google Analytics 4 measurement ID; empty = no GA4 tag
    # Google Consent Mode: analytics/ad cookies start "denied" here (EEA + UK + Switzerland)
    # and analytics "granted" everywhere else (ad cookies only once adsense_client is set).
    # A consent banner (CMP) can later flip them to granted.
    "consent_regions": [
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
        "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",  # EU
        "GF", "GP", "MQ", "RE", "YT", "MF", "AX",  # EU territories Google geolocates under their own codes
        "IS", "LI", "NO",  # rest of the EEA
        "GB", "CH",
    ],
    "privacy_updated": "November 6, 2026",  # bump whenever privacy.html text changes
    "language": "en",
}

# IndexNow (Bing, Yandex, Seznam, Naver): a public key, served as /<key>.txt to prove we own the host
INDEXNOW_KEY = "36bf3447839bd9e4905fcd0232434aa0"

# Key dates --------------------------------------------------------------
ELECTION_DAY_2028 = date(2028, 11, 7)
MIDTERM_DAY_2026 = date(2026, 11, 3)
IOWA_CAUCUS_2028 = None  # set once the DNC/RNC calendars are published
INAUGURATION_2029 = date(2029, 1, 20)

# When each kind of hand-maintained page last changed in substance: its sitemap lastmod and on-page date.
# Bump the entry in the same commit that changes the page (data pages date themselves from their data).
PAGE_REVISED = {
    "results": date(2026, 10, 31),      # state and year results pages, the 2028 map (certified 1976-2024 data)
    "scorecard": date(2026, 11, 3),     # /pollsters/ and pollster pages without a recent poll
    "methodology": date(2026, 11, 3),
    "about": date(2026, 11, 4),
}

# DNC: early window approved by the full DNC on August 15, 2026 (Rules and Bylaws proposal of July 24).
# RNC: its nominating-process committee voted in September 2026 to keep Iowa first; no dates are set.
DNC_CALENDAR_SOURCE = "https://washingtonstatestandard.com/2026/08/15/repub/dnc-approves-2028-presidential-nominating-cycle-starting-in-south-carolina-nevada/"
BALLOTPEDIA_DNC_SOURCE = "https://news.ballotpedia.org/2026/07/31/democratic-national-committee-announces-proposed-early-states-for-2028-democratic-presidential-calendar/"
FHQ_CALENDAR = "https://www.frontloadinghq.com/p/the-2028-presidential-primary-calendar.html"
RNC_IOWA_SOURCE = "https://www.kttc.com/2026/09/10/gop-keep-iowa-first-2028-primary-caucus-calendar/"

PRIMARY_CALENDAR_2028 = [
    # (when, what, note, source url, status): status "set" (party-approved) or "tentative"
    ("Jan 2028", "Republican contests begin in Iowa, then New Hampshire",
     "The RNC's nominating-process committee voted in September 2026 to keep Iowa first. No dates are set; Jan 3 (Iowa) and Jan 11 (New Hampshire) are estimates.", RNC_IOWA_SOURCE, "tentative"),
    ("Jan 22, 2028", "South Carolina Democratic primary", "First contest on the Democratic calendar approved by the DNC on August 15, 2026.", DNC_CALENDAR_SOURCE, "set"),
    ("Feb 1, 2028", "Nevada Democratic primary", "DNC-approved early window.", DNC_CALENDAR_SOURCE, "set"),
    ("Feb 8, 2028", "New Hampshire Democratic primary", "DNC-approved date; New Hampshire law requires its primary to come first, so the state-run primary may be earlier and this contest party-run.", FHQ_CALENDAR, "tentative"),
    ("Feb 15, 2028", "New Mexico Democratic primary", "DNC-approved date; New Mexico law currently sets its primary in June, so the date needs a law change or a party-run contest.", FHQ_CALENDAR, "tentative"),
    ("Feb 22, 2028", "Michigan Democratic primary", "DNC-approved date; Michigan law already sets the fourth Tuesday in February.", DNC_CALENDAR_SOURCE, "set"),
    ("Feb 29, 2028", "Virginia Democratic primary", "DNC-approved date; Virginia law currently holds its primary on Super Tuesday, so it needs a law change.", FHQ_CALENDAR, "tentative"),
    ("Mar 7, 2028", "Super Tuesday", "The largest single day of delegate allocation; about 14 states are scheduled so far.", FHQ_CALENDAR, "set"),
    ("Jun 2028", "Final primaries", "Nominating season ends.", "", "tentative"),
    ("Jul–Aug 2028", "National conventions", "Nominees formally selected.", "", "tentative"),
    ("Sep–Oct 2028", "General election debates", "Dates set by the Commission on Presidential Debates or the campaigns.", "", "tentative"),
    ("Nov 7, 2028", "Election Day", "Set by federal law: the Tuesday after the first Monday in November.", "", "set"),
    ("Dec 2028", "Electors meet", "Electoral College votes are cast in state capitals.", "", "set"),
    ("Jan 6, 2029", "Congress counts electoral votes", "", "", "set"),
    ("Jan 20, 2029", "Inauguration Day", "", "", "set"),
]
CALENDAR_CHECKED = "November 3, 2026"

# 2028 candidate status. Everyone in the primary averages is "not declared" unless listed here with a source.
# Statuses: "declared" (formal launch), "exploratory" (exploratory committee), "ruled out" (said they will not run).
CANDIDATES_CHECKED = "November 6, 2026"
REUTERS_2028_FIELD = "https://www.yahoo.com/news/politics/articles/midterms-over-democrats-plunge-wide-111023616.html"
CANDIDATE_STATUS_2028 = {
    # name: (status, public statement, source url)
    "JD Vance": ("not declared", 'Has said there is "a chance" he will not run, citing family considerations.', REUTERS_2028_FIELD),
    "Marco Rubio": ("not declared", 'Has said he has "no plans at this time" to run for president.', REUTERS_2028_FIELD),
    "Ron DeSantis": ("not declared", "Has declined to rule out another run.", REUTERS_2028_FIELD),
}

# Analysis pieces and the day each was first published (datePublished never moves)
ANALYSIS_PUBLISHED = {
    "final-generic-ballot-2026": date(2026, 11, 3),
}

# Party colours used across charts (kept muted for accessibility)
PARTY_COLORS = {
    "DEM": "#1e40af",
    "REP": "#b91c1c",
    "IND": "#7c3aed",
    "GRN": "#16a34a",
    "LIB": "#ca8a04",
    "OTHER": "#6b7280",
    "approve": "#1f7a4d",
    "disapprove": "#b91c1c",
    "undecided": "#9ca3af",
}


@dataclass
class Race:
    """A pollable contest or tracker rendered as one page."""

    id: str
    title: str
    slug: str  # output path, e.g. "2028/president/vance-vs-newsom"
    kind: str  # general | primary | approval | generic
    description: str
    candidates: list[str] = field(default_factory=list)
    parties: dict[str, str] = field(default_factory=dict)
    wikipedia_page: str | None = None  # page title used by fetch_wikipedia
    wikipedia_section_hint: str | None = None  # substring of the section/table heading
    half_life_days: int = 30
    menu: bool = True
    featured: bool = False
    short: str = ""  # compact label for tables

    @property
    def short_title(self) -> str:
        return self.short or self.title


RACES: list[Race] = [
    Race(
        id="approval-trump-2",
        short="Trump approval",
        title="Trump Approval Rating Tracker",
        slug="approval/trump",
        kind="approval",
        description="Daily-updated polling average of President Trump's job approval, with every underlying poll and pollster.",
        candidates=["Approve", "Disapprove"],
        parties={"Approve": "approve", "Disapprove": "disapprove"},
        wikipedia_page="Opinion_polling_on_the_second_Trump_presidency",
        wikipedia_section_hint="Nationwide job approval",
        half_life_days=14,
        featured=True,
    ),
    Race(
        id="pres-2028-vance-newsom",
        short="Vance vs. Newsom",
        title="2028 Presidential Election Polls: Vance vs. Newsom",
        slug="2028/president/vance-vs-newsom",
        kind="general",
        description="Polling average for the most-tested hypothetical 2028 general election matchup: JD Vance (R) against Gavin Newsom (D).",
        candidates=["JD Vance", "Gavin Newsom"],
        parties={"JD Vance": "REP", "Gavin Newsom": "DEM"},
        wikipedia_page="Nationwide_opinion_polling_for_the_2028_United_States_presidential_election",
        wikipedia_section_hint="Vance vs. Newsom",
        half_life_days=45,
        featured=True,
    ),
    Race(
        id="pres-2028-vance-ocasio-cortez",
        short="Vance vs. Ocasio-Cortez",
        title="2028 Presidential Election Polls: Vance vs. Ocasio-Cortez",
        slug="2028/president/vance-vs-ocasio-cortez",
        kind="general",
        description="Polling average for a hypothetical JD Vance (R) vs. Alexandria Ocasio-Cortez (D) 2028 general election.",
        candidates=["JD Vance", "Alexandria Ocasio-Cortez"],
        parties={"JD Vance": "REP", "Alexandria Ocasio-Cortez": "DEM"},
        wikipedia_page="Nationwide_opinion_polling_for_the_2028_United_States_presidential_election",
        wikipedia_section_hint="Vance vs. Ocasio-Cortez",
        half_life_days=45,
    ),
    Race(
        id="pres-2028-vance-buttigieg",
        short="Vance vs. Buttigieg",
        title="2028 Presidential Election Polls: Vance vs. Buttigieg",
        slug="2028/president/vance-vs-buttigieg",
        kind="general",
        description="Polling average for a hypothetical JD Vance (R) vs. Pete Buttigieg (D) 2028 general election.",
        candidates=["JD Vance", "Pete Buttigieg"],
        parties={"JD Vance": "REP", "Pete Buttigieg": "DEM"},
        wikipedia_page="Nationwide_opinion_polling_for_the_2028_United_States_presidential_election",
        wikipedia_section_hint="Vance vs. Buttigieg",
        half_life_days=45,
    ),
    Race(
        id="dem-primary-2028",
        short="Dem primary",
        title="2028 Democratic Primary Polls",
        slug="2028/democratic-primary",
        kind="primary",
        description="National polling average for the 2028 Democratic presidential nomination.",
        candidates=["Gavin Newsom", "Kamala Harris", "Pete Buttigieg", "Alexandria Ocasio-Cortez", "Josh Shapiro", "Andy Beshear", "Cory Booker", "Other/Undecided"],
        parties={c: "DEM" for c in ["Gavin Newsom", "Kamala Harris", "Pete Buttigieg", "Alexandria Ocasio-Cortez", "Josh Shapiro", "Andy Beshear", "Cory Booker"]} | {"Other/Undecided": "undecided"},
        wikipedia_page="Nationwide_opinion_polling_for_the_2028_Democratic_Party_presidential_primaries",
        wikipedia_section_hint="National",
        half_life_days=60,
        featured=True,
    ),
    Race(
        id="gop-primary-2028",
        short="GOP primary",
        title="2028 Republican Primary Polls",
        slug="2028/republican-primary",
        kind="primary",
        description="National polling average for the 2028 Republican presidential nomination.",
        candidates=["JD Vance", "Marco Rubio", "Ron DeSantis", "Donald Trump Jr.", "Nikki Haley", "Robert F. Kennedy Jr.", "Other/Undecided"],
        parties={c: "REP" for c in ["JD Vance", "Marco Rubio", "Ron DeSantis", "Donald Trump Jr.", "Nikki Haley", "Robert F. Kennedy Jr."]} | {"Other/Undecided": "undecided"},
        wikipedia_page="Nationwide_opinion_polling_for_the_2028_Republican_Party_presidential_primaries",
        wikipedia_section_hint="National",
        half_life_days=60,
        featured=True,
    ),
    Race(
        id="generic-ballot-2026",
        short="Generic ballot",
        title="2026 Generic Congressional Ballot",
        slug="2026/generic-ballot",
        kind="generic",
        description="Polling average of the national generic congressional ballot ahead of the November 3, 2026 midterm elections.",
        candidates=["Democrats", "Republicans"],
        parties={"Democrats": "DEM", "Republicans": "REP"},
        wikipedia_page="2026_United_States_elections",
        wikipedia_section_hint="Polling",
        half_life_days=14,
        featured=True,
    ),
]

RACE_BY_ID = {r.id: r for r in RACES}

# Prediction markets -----------------------------------------------------
# Polymarket "gamma" API event slugs. Verify these against the live site; markets get renamed
# between cycles. Kalshi lists the same contests; it is linked from /markets/, not republished.
KALSHI_URL = "https://kalshi.com/"
MARKETS = [
    {
        "id": "pres-2028-winner",
        "title": "2028 Presidential Election Winner",
        "polymarket_slug": "presidential-election-winner-2028",
        "compare_race": None,
    },
    {
        "id": "dem-nominee-2028",
        "title": "2028 Democratic Nominee",
        "polymarket_slug": "democratic-presidential-nominee-2028",
        "compare_race": "dem-primary-2028",
    },
    {
        "id": "gop-nominee-2028",
        "title": "2028 Republican Nominee",
        "polymarket_slug": "republican-presidential-nominee-2028",
        "compare_race": "gop-primary-2028",
    },
]

# 538 letter grades -> averaging weight. Unrated pollsters get 0.6.
GRADE_WEIGHTS = {
    "A+": 1.0, "A": 0.95, "A-": 0.9, "A/B": 0.85,
    "B+": 0.8, "B": 0.75, "B-": 0.7, "B/C": 0.65,
    "C+": 0.6, "C": 0.55, "C-": 0.5, "C/D": 0.45,
    "D+": 0.4, "D": 0.35, "D-": 0.3, "F": 0.1,
}
DEFAULT_GRADE_WEIGHT = 0.6

# Social bot (X / Twitter) -------------------------------------------------
BOT = {
    "handle": "@ElectionsUSAorg",               # e.g. "@electionsusa" (shown on cards when set)
    "fresh_days": 10,             # only announce polls whose fieldwork ended this recently
    "max_posts_per_run": 1,       # four runs a day at U.S. hours -> one post each, spaced out
    "max_posts_per_day": 6,
    "include_links": False,       # X charges ~13x more for posts containing a URL
    "hashtags": [],               # e.g. ["#2028Election"]; keep it to one at most
    "roundup_weekday": 0,         # Monday (UTC)
    "election_milestones": [700, 600, 500, 400, 365, 300, 250, 200, 150, 100, 75, 60, 50, 45,
                            30, 21, 14, 10, 7, 6, 5, 4, 3, 2, 1, 0],
    "midterm_milestones": [30, 14, 7, 3, 1, 0],
    # One-off posts that link a page, each sent once inside its UTC window. They carry a link on
    # purpose, so each costs more than a normal post (see include_links).
    "campaigns": [
        {"key": "campaign:2026-midterm-day", "race": "generic-ballot-2026", "moment": "day",
         "start": "2026-11-03T12:00:00+00:00", "end": "2026-11-04T00:00:00+00:00"},
        {"key": "campaign:2026-midterm-after", "race": "generic-ballot-2026", "moment": "after",
         "start": "2026-11-04T12:00:00+00:00", "end": "2026-11-05T12:00:00+00:00"},
    ],
}
