"""Fetch poll tables from Wikipedia via the MediaWiki API and normalise them.

Wikipedia's polling pages are community-maintained compilations of primary
sources (each row cites the pollster's own release). We parse the rendered HTML
tables (action=parse) and keep the row's citation URL as `source_url` when
available, falling back to the Wikipedia page URL.

Table layouts differ between pages and change over time, so parsing is
heuristic and defensive: a table is used only if we can identify a pollster
column, a date column and at least two candidate columns from `race.candidates`.
Unparseable rows are skipped and logged, never guessed.

Attribution: Wikipedia text is CC BY-SA 4.0; poll numbers themselves are facts.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup

from . import config
from .schema import POLL_COLUMNS, canonical_pollster, make_poll_id, now_iso

log = logging.getLogger(__name__)
API = "https://en.wikipedia.org/w/api.php"
UA = f"ElectionsUSA-bot/1.0 (+{config.SITE['url']}; {config.SITE['contact_email']})"

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

CANDIDATE_ALIASES = {
    "vance": "JD Vance", "newsom": "Gavin Newsom", "ocasio-cortez": "Alexandria Ocasio-Cortez",
    "ocasio cortez": "Alexandria Ocasio-Cortez", "aoc": "Alexandria Ocasio-Cortez",
    "buttigieg": "Pete Buttigieg", "harris": "Kamala Harris", "shapiro": "Josh Shapiro",
    "beshear": "Andy Beshear", "booker": "Cory Booker", "rubio": "Marco Rubio",
    "desantis": "Ron DeSantis", "trump jr": "Donald Trump Jr.", "haley": "Nikki Haley",
    "kennedy": "Robert F. Kennedy Jr.", "approve": "Approve", "disapprove": "Disapprove",
    "democrat": "Democrats", "democratic": "Democrats", "republican": "Republicans",
    "undecided": "Other/Undecided", "other": "Other/Undecided",
}


def fetch_page_html(title: str, session: requests.Session | None = None) -> str:
    s = session or requests.Session()
    r = s.get(API, params={"action": "parse", "page": title, "prop": "text", "format": "json",
                           "formatversion": 2, "redirects": 1}, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    js = r.json()
    if "error" in js:
        raise RuntimeError(js["error"])
    return js["parse"]["text"]


def parse_date_range(text: str, default_year: int | None = None) -> tuple[date | None, date | None]:
    """Parse strings like 'Oct 13–14, 2025', 'September 28 – October 4, 2026', 'Jul 1–4, 2026'."""
    t = re.sub(r"\[.*?\]", "", str(text)).replace("–", "-").replace("—", "-").replace(" ", " ")
    t = re.sub(r"\s+", " ", t).strip()
    year_m = re.search(r"(20\d\d)", t)
    year = int(year_m.group(1)) if year_m else default_year
    if not year:
        return None, None
    parts = [p.strip() for p in t.split("-")]
    try:
        if len(parts) == 1:
            d = _parse_single(parts[0], year)
            return d, d
        a, b = parts[0], parts[1]
        start = _parse_single(a, year)
        day_only = re.fullmatch(r"(\d{1,2})(?:\s*,?\s*(20\d\d))?", b.replace(",", " ").strip())
        if day_only and start:
            # 'Oct 13' + '14, 2025' -> end shares the start month
            end = date(year, start.month, int(day_only.group(1)))
            if start.year != year and start.month == end.month:
                start = date(year, start.month, start.day)
        else:
            end = _parse_single(b, year)
            if start is None and end is not None:
                m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})", a)
                if m and m.group(1)[:3].lower() in MONTHS:
                    start = date(end.year, MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
        if start and end and start > end:
            start = date(end.year - 1, start.month, start.day)
        return start, end
    except (ValueError, KeyError):
        return None, None


def _parse_single(s: str, year: int) -> date | None:
    s = s.replace(",", " ").strip()
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})(?:\s+(20\d\d))?", s)
    if m:
        mon = MONTHS.get(m.group(1)[:3].lower())
        if not mon:
            return None
        y = int(m.group(3)) if m.group(3) else year
        return date(y, mon, int(m.group(2)))
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)(?:\s+(20\d\d))?", s)
    if m:
        mon = MONTHS.get(m.group(2)[:3].lower())
        if not mon:
            return None
        y = int(m.group(3)) if m.group(3) else year
        return date(y, mon, int(m.group(1)))
    return None


def parse_sample(text: str) -> tuple[float | None, str]:
    t = str(text).replace(",", "")
    n = re.search(r"(\d{3,6})", t)
    pop = ""
    tl = t.lower()
    if "(lv)" in tl or " lv" in tl or tl.endswith("lv"):
        pop = "LV"
    elif "(rv)" in tl or " rv" in tl or tl.endswith("rv"):
        pop = "RV"
    elif "(a)" in tl or " a" == tl[-2:] or "adults" in tl:
        pop = "A"
    return (float(n.group(1)) if n else None), pop


def match_candidate(header: str, race: config.Race) -> str | None:
    h = re.sub(r"\[.*?\]", "", str(header)).strip().lower()
    for cand in race.candidates:
        last = cand.split()[-1].lower().rstrip(".")
        if cand.lower() in h or (last in h and len(last) > 3):
            return cand
    for alias, cand in CANDIDATE_ALIASES.items():
        if alias in h and cand in race.candidates:
            return cand
    return None


def tables_for_race(html: str, race: config.Race) -> list[tuple[pd.DataFrame, list[str]]]:
    """Return (dataframe, row_citation_urls) for every wikitable that fits the race."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tbl in soup.select("table.wikitable"):
        heading = ""
        prev = tbl.find_previous(["h2", "h3", "h4"])
        if prev:
            heading = prev.get_text(" ", strip=True)
        if race.wikipedia_section_hint and race.kind == "general":
            # for head-to-head pages, require the matchup heading to match
            if race.wikipedia_section_hint.lower().replace(".", "") not in heading.lower().replace(".", ""):
                continue
        try:
            df = pd.read_html(StringIO(str(tbl)), flavor="lxml")[0]
        except ValueError:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(str(x) for x in col if "Unnamed" not in str(x)).strip() for col in df.columns]
        cols = [str(c) for c in df.columns]
        cand_cols = [c for c in cols if match_candidate(c, race)]
        if len(set(match_candidate(c, race) for c in cand_cols)) < 2:
            continue
        if not any(re.search(r"poll|source|pollster", c, re.I) for c in cols):
            continue
        if not any(re.search(r"date", c, re.I) for c in cols):
            continue
        # citation URLs per row (first external link in first cell)
        urls = []
        for tr in tbl.select("tr"):
            tds = tr.find_all(["td"])
            if not tds:
                continue
            a = tds[0].find("a", href=True)
            href = a["href"] if a else ""
            if href.startswith("/wiki/"):
                href = ""
            urls.append(href if href.startswith("http") else "")
        out.append((df, urls))
    return out


def rows_from_table(df: pd.DataFrame, urls: list[str], race: config.Race, page_url: str) -> list[dict]:
    cols = [str(c) for c in df.columns]
    poll_col = next(c for c in cols if re.search(r"poll|source|pollster", c, re.I))
    date_col = next(c for c in cols if re.search(r"date", c, re.I))
    sample_col = next((c for c in cols if re.search(r"sample", c, re.I)), None)
    cand_map = {c: match_candidate(c, race) for c in cols if match_candidate(c, race)}
    rows: list[dict] = []
    for i, r in df.iterrows():
        pollster_raw = str(r[poll_col])
        if not pollster_raw or pollster_raw.lower() in ("nan", poll_col.lower()):
            continue
        start, end = parse_date_range(r[date_col])
        if end is None:
            log.debug("skip row (date): %s | %s", pollster_raw, r[date_col])
            continue
        n, pop = parse_sample(r[sample_col]) if sample_col else (None, "")
        sponsor = ""
        pollster = canonical_pollster(re.split(r"/| for ", re.sub(r"\[.*?\]", "", pollster_raw))[0])
        if "/" in pollster_raw:
            sponsor = pollster_raw.split("/", 1)[1].strip()
        url = urls[i] if i < len(urls) and urls[i] else page_url
        pid = make_poll_id(race.id, pollster, end.isoformat(), pop)
        got = 0
        for col, cand in cand_map.items():
            val = str(r[col]).replace("%", "").strip()
            m = re.match(r"^-?\d+(\.\d+)?", val)
            if not m:
                continue
            pct = float(m.group(0))
            if 0 <= pct <= 100:
                rows.append(dict(poll_id=pid, race_id=race.id, pollster=pollster, sponsor=sponsor,
                                 start_date=(start or end).isoformat(), end_date=end.isoformat(),
                                 sample_size=n, population=pop, candidate=cand, pct=pct,
                                 source_url=url, source_type="wikipedia", notes="", fetched_at=now_iso()))
                got += 1
        if got < 2:
            # drop partial rows for this poll
            rows = [x for x in rows if x["poll_id"] != pid]
    return rows


def fetch_race(race: config.Race, session: requests.Session | None = None) -> pd.DataFrame:
    if not race.wikipedia_page:
        return pd.DataFrame(columns=POLL_COLUMNS)
    page_url = f"https://en.wikipedia.org/wiki/{race.wikipedia_page}"
    html = fetch_page_html(race.wikipedia_page, session)
    rows: list[dict] = []
    for df, urls in tables_for_race(html, race):
        rows.extend(rows_from_table(df, urls, race, page_url))
    log.info("%s: %d candidate-rows from Wikipedia", race.id, len(rows))
    return pd.DataFrame(rows, columns=POLL_COLUMNS)


def fetch_all(session: requests.Session | None = None) -> pd.DataFrame:
    s = session or requests.Session()
    frames = []
    for race in config.RACES:
        try:
            frames.append(fetch_race(race, s))
        except Exception as e:  # network or layout change: keep going, keep old data
            log.warning("%s: fetch failed: %s", race.id, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=POLL_COLUMNS)
