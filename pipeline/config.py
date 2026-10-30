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
    "tagline": "Open poll averages, pollster scorecards and market odds for the 2028 U.S. election",
    "description": (
        "Transparent, free polling averages for the 2028 presidential election, "
        "the Democratic and Republican primaries, presidential approval, "
        "pollster accuracy ratings and prediction-market odds. Open data, open methodology."
    ),
    "author": "ElectionsUSA Data Desk",  # TODO: replace with a named author for E-E-A-T
    "contact_email": "hello@electionsusa.org",
    "twitter": "@ElectionsUSAorg",  # e.g. "@electionsusa"
    "github_repo": "erenmentese/electionsusa",  # e.g. "yourname/electionsusa" (enables data-download links)
    "adsense_client": "",  # e.g. "ca-pub-1234567890123456"; empty = render placeholders
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
    "privacy_updated": "October 29, 2026",  # bump whenever privacy.html text changes
    "language": "en",
}

# Key dates --------------------------------------------------------------
ELECTION_DAY_2028 = date(2028, 11, 7)
MIDTERM_DAY_2026 = date(2026, 11, 3)
IOWA_CAUCUS_2028 = None  # set once the DNC/RNC calendars are published
INAUGURATION_2029 = date(2029, 1, 20)

PRIMARY_CALENDAR_2028 = [
    # (approximate month, label, note) - update as parties publish the calendar
    ("Jan-Feb 2028", "First nominating contests", "Order is set by each party; Iowa/New Hampshire/South Carolina/Nevada traditionally lead."),
    ("Mar 2028", "Super Tuesday", "The largest single day of delegate allocation."),
    ("Jun 2028", "Final primaries", "Nominating season ends."),
    ("Jul-Aug 2028", "National conventions", "Nominees formally selected."),
    ("Sep-Oct 2028", "General election debates", "Dates set by the Commission on Presidential Debates or the campaigns."),
    ("Nov 7, 2028", "Election Day", "Polls close; counting begins."),
    ("Dec 2028", "Electors meet", "Electoral College votes are cast in state capitals."),
    ("Jan 6, 2029", "Congress counts electoral votes", ""),
    ("Jan 20, 2029", "Inauguration Day", ""),
]

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
# Polymarket "gamma" API event slugs and Kalshi series tickers. Verify these
# against the live sites; markets get renamed between cycles.
MARKETS = [
    {
        "id": "pres-2028-winner",
        "title": "2028 Presidential Election Winner",
        "polymarket_slug": "presidential-election-winner-2028",
        "kalshi_series": "KXPRESNOM2028",  # placeholder: confirm ticker on kalshi.com
        "compare_race": None,
    },
    {
        "id": "dem-nominee-2028",
        "title": "2028 Democratic Nominee",
        "polymarket_slug": "democratic-presidential-nominee-2028",
        "kalshi_series": "KXDEMNOM2028",
        "compare_race": "dem-primary-2028",
    },
    {
        "id": "gop-nominee-2028",
        "title": "2028 Republican Nominee",
        "polymarket_slug": "republican-presidential-nominee-2028",
        "kalshi_series": "KXREPNOM2028",
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
    "max_posts_per_run": 2,       # the workflow runs every 6h -> at most ~8 posts/day
    "max_posts_per_day": 6,
    "include_links": False,       # X charges ~13x more for posts containing a URL
    "hashtags": [],               # e.g. ["#2028Election"]; keep it to one at most
    "roundup_weekday": 0,         # Monday (UTC)
    "election_milestones": [700, 600, 500, 400, 365, 300, 250, 200, 150, 100, 75, 60, 50, 45,
                            30, 21, 14, 10, 7, 6, 5, 4, 3, 2, 1, 0],
    "midterm_milestones": [30, 14, 7, 3, 1, 0],
}
