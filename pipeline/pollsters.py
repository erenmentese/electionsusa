"""Pollster pages: /pollsters/<slug>/ for every rated pollster and every active one.

Wikipedia's poll tables often put the media sponsor first ("The Economist/YouGov",
"CNN/SSRS") and the fetcher keeps the first name, so the pollster column of
data/polls.csv can hold a newspaper, a typo or a partisan tag. `resolve()` maps a
poll's pollster and sponsor columns to the organisation that actually ran it, which
is what a pollster page is about. The data itself is left as published.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from . import scorecard

MIN_POLLS = 5  # an unrated pollster needs this many polls on record for a page of its own

BEACON = "Beacon Research/Shaw & Co. Research"  # the Fox News poll
NYT_SIENA = "The New York Times/Siena College"

# Outlets and sponsors that commission polls but don't run them. When one is named as the
# pollster, the poll belongs to the first name in the sponsor column that isn't one of these.
MEDIA = {"abcnews", "aarp", "argument", "bulwark", "cbs", "cbsnews", "cnn", "dailymail",
         "deseretnewsandhinckleyinstituteofpolitics", "economist", "financialtimes", "harvard", "harvardcaps",
         "ii", "nbcnews", "newsnation", "npr", "onpoint", "pablotorrefindsout", "pablotorresfindsout", "pbs", "reuters",
         "strengthinnumbers", "washingtonpost", "yahoo", "yahoonews"}

# Spelling variants, renamed firms and sponsors with a standing partner -> the name on the page
ALIASES = {
    "ap": "AP-NORC", "apnorc": "AP-NORC", "associatedpress": "AP-NORC",
    "atlasintel": "AtlasIntel",
    "beacon": BEACON, "beaconresearch": BEACON, "beaconresearchandshawcompanyresearch": BEACON, "foxnews": BEACON,
    "bgsu": "Bowling Green State University",
    "co": "co/efficient", "coefficient": "co/efficient",
    "data": "Data for Progress",  # "Data for Progress", cut at " for " by the fetcher
    "ddhq": "Decision Desk HQ",
    "fabrizio": "Fabrizio Ward",
    "harris": "HarrisX", "harrispoll": "HarrisX", "harvardharris": "HarrisX",
    "hartresearch": "Hart Research Associates",
    "insideradvantage": "InsiderAdvantage",
    "jlpartners": "J.L. Partners",
    "leger360": "Leger",
    "marist": "Marist University", "maristcollege": "Marist University",
    "marquetteuniversity": "Marquette University Law School",
    "mclauglinassociates": "McLaughlin & Associates",
    "napolitan": "RMG Research", "napolitannews": "RMG Research", "napolitannewsservice": "RMG Research",
    "newyorktimes": NYT_SIENA,
    "noblepredictiveinsight": "Noble Predictive Insights", "npi": "Noble Predictive Insights",
    "quinnipacuniversity": "Quinnipiac University",
    "surveymonkey": "SurveyMonkey",
    "tipp": "TIPP Insights", "tippinsights": "TIPP Insights",
    "trafalgar": "Trafalgar Group",
    "tuftpublicopinionlab": "Tufts University",
    "universityofmassachusettslowell": "UMass Lowell",
    "zogby": "Zogby Analytics",
}
NOT_POLLSTERS = {"538aggregate"}

# Firms FiveThirtyEight rated under an earlier or longer name
RATED_AS = {
    "Decision Desk HQ": "NewsNation",  # 538 rated the NewsNation poll, which DDHQ runs, under the sponsor's name
    "Hart Research Associates": "Hart Research Associates/Public Opinion Strategies",  # the NBC News poll, with POS
    "High Point University": "High Point University Survey Research Center",
    "Marist University": "Marist College",
    "Navigator Research": "Global Strategy Group/GBAO (Navigator Research)",
    "Noble Predictive Insights": "OH Predictive Insights",
    "Tufts University": "Tufts University Public Opinion Lab",
    "UMass Lowell": "University of Massachusetts Lowell Center for Public Opinion",
}

RACE_TYPES = {"Pres-G": "President", "Pres-P": "Presidential primary", "Sen-G": "Senate", "Gov-G": "Governor",
              "House-G": "House"}


def key(name: str) -> str:
    n = re.sub(r"\[.*?\]|\((?:R|D)\)", "", str(name)).lower().strip()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^the\s+", "", n))


def clean(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[.*?\]|\((?:R|D)\)", "", str(name))).strip()


def resolve(pollster: str, sponsor: str | None = "") -> tuple[str, str] | None:
    """(firm, party tag) for one poll; the tag is "R" or "D" when the source marks the firm as partisan."""
    names = [n for n in f"{pollster}/{sponsor if isinstance(sponsor, str) else ''}".split("/") if key(n)]
    if not names or key(names[0]) in NOT_POLLSTERS:
        return None
    pick = next((n for n in names if key(n) in ALIASES or key(n) not in MEDIA), names[0])
    tag = m.group(1) if (m := re.search(r"\((R|D)\)", pick)) else ""
    if tag and any(f"({'D' if tag == 'R' else 'R'})" in n for n in names):
        tag = ""  # a bipartisan team, like Beacon (D) and Shaw (R) for Fox News
    return ALIASES.get(key(pick), clean(pick)), tag


def firm(pollster: str, sponsor: str | None = "") -> str | None:
    r = resolve(pollster, sponsor)
    return r[0] if r else None


def slugify(name: str) -> str:
    s = re.sub(r"^the\s+", "", name.lower()).replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


@dataclass
class Pollster:
    name: str
    slug: str = ""
    rated: scorecard.PollsterRow | None = None
    rank: int | None = None
    polls: list[dict] = field(default_factory=list)  # newest first
    tags: Counter = field(default_factory=Counter)

    @property
    def path(self) -> str:
        return f"/pollsters/{self.slug}/"

    @property
    def partisan(self) -> str:
        """"R" or "D" when the source tables tag most of this pollster's polls as partisan."""
        tag, n = (self.tags.most_common(1) or [("", 0)])[0]
        return tag if tag and 2 * n > len(self.polls) else ""


def registry(polls: list[dict], rated: list[scorecard.PollsterRow]) -> dict[str, Pollster]:
    """Every pollster that gets a page, keyed by `key(name)`.

    polls: one dict per poll, newest first, each with a "firm" and "tag" (see `resolve`).
    rated: the historical scorecard, best first.
    """
    out = {key(r.pollster): Pollster(name=r.pollster, rated=r, rank=i) for i, r in enumerate(rated, start=1)}
    for name, old in RATED_AS.items():
        if key(old) in out:
            out[key(name)] = out.pop(key(old))
            out[key(name)].name = name
    spellings: dict[str, Counter] = {}
    for p in polls:
        if not p["firm"]:
            continue
        k = key(p["firm"])
        if k not in out:
            spellings.setdefault(k, Counter())[p["firm"]] += 1
            out[k] = Pollster(name="")
        out[k].polls.append(p)
        out[k].tags[p["tag"]] += 1
    for k, c in spellings.items():
        if len(out[k].polls) < MIN_POLLS:
            del out[k]
        else:
            out[k].name = c.most_common(1)[0][0]
    used: set[str] = set()
    for p in sorted(out.values(), key=lambda p: (p.rank is None, p.rank or 0, p.name)):
        p.slug = slugify(p.name)
        while p.slug in used:
            p.slug += "-2"
        used.add(p.slug)
    return out


def track_record(raw: pd.DataFrame, rating_id: int, min_year: int = 2016) -> dict[str, list[dict]]:
    """The rated polls behind a scorecard row, broken down by election year and by race type."""
    g = raw[(raw["pollster_rating_id"] == rating_id) & (raw["year"] >= min_year) & raw["error"].notna()]

    def rows(by, label) -> list[dict]:
        return [dict(label=label(v), n=len(s), error=round(float(s["error"].mean()), 1),
                     bias=round(float(s["bias"].mean()), 1) if s["bias"].notna().any() else None,
                     bias_label=scorecard._bias_label(float(s["bias"].mean())) if s["bias"].notna().any() else "n/a",
                     right_call=round(100 * float(s["rightcall"].mean())))
                for v, s in g.groupby(by)]

    by_type = sorted(rows("type_simple", lambda t: RACE_TYPES.get(t, t)), key=lambda r: -r["n"])
    return {"years": rows("year", str), "types": by_type}


def answer_sentence(p: Pollster, n_rated: int) -> str:
    """The page lead and meta description: the pollster's record in one quotable sentence."""
    r = p.rated
    if r:
        lean = ("Its misses showed no consistent partisan lean" if abs(r.mean_bias) < 0.3 else
                f"On average its polls leaned {abs(r.mean_bias):.1f} points toward "
                f"{'Democrats' if r.mean_bias > 0 else 'Republicans'}")
        return (f"{possessive(p.name)} {r.n_polls} polls in the final three weeks of {r.cycles} races missed the "
                f"final margin by {r.mean_abs_error:.1f} points on average, ranking {ordinal(p.rank)} of {n_rated} "
                f"pollsters on the ElectionsUSA scorecard. {lean}, and {r.right_call_pct:.0f}% had the eventual winner ahead.")
    first = min(q["end_date"] for q in p.polls)
    return (f"ElectionsUSA has recorded {len(p.polls)} {p.name} polls since {first.strftime('%B %Y')}, the latest "
            f"ending {p.polls[0]['end_date'].strftime('%B %-d, %Y')}. It is not on the accuracy scorecard yet, which "
            f"needs at least ten final-three-weeks polls since 2016 in FiveThirtyEight's archive.")


def field_error(raw: pd.DataFrame, min_year: int = 2016) -> float:
    """Mean error of every rated poll since `min_year`: the yardstick for one pollster's average error."""
    return float(raw[(raw["year"] >= min_year) & raw["error"].notna()]["error"].mean())


def partners(pollster: str, sponsor: str | None, name: str) -> str:
    """The other organisations named on a poll (its media sponsor or co-pollster), for display."""
    names = f"{pollster}/{sponsor if isinstance(sponsor, str) else ''}".split("/")
    return " / ".join(clean(n) for n in names if key(n) and key(n) != key(name) and ALIASES.get(key(n)) != name)
