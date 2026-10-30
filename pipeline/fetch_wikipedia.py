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
    # longest names first so "Disapprove" is not swallowed by "Approve"
    for cand in sorted(race.candidates, key=len, reverse=True):
        last = cand.split()[-1].lower().rstrip(".")
        if cand.lower() in h or (last in h and len(last) > 3):
            return cand
    for alias, cand in sorted(CANDIDATE_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if alias in h and cand in race.candidates:
            return cand
    return None


NON_CANDIDATE_COLS = re.compile(
    r"poll|source|date|sample|margin|moe|error|undecided|other|unsure|lead|net|notes?|ref|link|method|mode|spread|total", re.I)
PARTY_LABEL = re.compile(r"\((?:D|R|I|L|G|Ind\.?|Dem\.?|Rep\.?)\)", re.I)


def _heading_year(text: str) -> int | None:
    """'October 2026' -> 2026, '2025–2026' -> 2026 (latest year), 'Nationwide' -> None."""
    ys = re.findall(r"(20\d\d)", text or "")
    return int(ys[-1]) if ys else None


def _headings(tbl) -> tuple[str, str]:
    """(nearest heading text, nearest h2 text) preceding the table."""
    near = tbl.find_previous(["h2", "h3", "h4", "h5"])
    h2 = tbl.find_previous("h2")
    clean = lambda h: re.sub(r"\[edit.*?\]", "", h.get_text(" ", strip=True)).strip() if h else ""
    return clean(near), clean(h2)


def tables_for_race(html: str, race: config.Race) -> list[tuple[pd.DataFrame, list[str], str]]:
    """Return (dataframe, row_citation_urls, heading) for every wikitable that fits the race.

    Selection is by table shape, not by section wording (Wikipedia editors rename
    sections often): a pollster column, a date column and the race's candidates.
    Aggregator tables (RealClearPolling, 270toWin ...) are skipped: they are not polls.
    """
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tbl in soup.select("table.wikitable"):
        heading, h2 = _headings(tbl)
        if re.search(r"aggregat", heading + " " + h2, re.I):
            continue
        if race.wikipedia_section_hint and race.kind in ("approval", "generic"):
            # these pages mix national tables with statewide/issue/Senate tables: stay in the right h2
            hint = race.wikipedia_section_hint.lower()
            if hint not in (heading + " " + h2).lower():
                continue
        for st in tbl.select("style"):
            st.decompose()
        try:
            df = pd.read_html(StringIO(str(tbl)), flavor="lxml")[0]
        except ValueError:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(str(x) for x in col if "Unnamed" not in str(x)).strip() for col in df.columns]
        cols = [str(c) for c in df.columns]
        if any(re.search(r"aggregat|updated", c, re.I) for c in cols):
            continue
        if not any(re.search(r"poll|source|pollster|firm", c, re.I) for c in cols):
            continue
        if not any(re.search(r"date", c, re.I) for c in cols):
            continue
        matched = {match_candidate(c, race) for c in cols if match_candidate(c, race)}
        matched.discard(None)
        if race.kind == "general":
            # exactly this two-way matchup: both candidates present, no third named candidate
            if matched != set(race.candidates):
                continue
            extra = [c for c in cols if not match_candidate(c, race) and not NON_CANDIDATE_COLS.search(c)]
            if extra or any(PARTY_LABEL.search(c) and not match_candidate(c, race) for c in cols):
                continue
        elif race.kind == "primary":
            if len(matched - {"Other/Undecided"}) < 3:  # skip head-to-head hypotheticals
                continue
        elif len(matched) < 2:
            continue
        # citation URLs per row (first external, non-Wikipedia link in the first cell)
        urls = []
        for tr in tbl.select("tr"):
            tds = tr.find_all(["td"])
            if not tds:
                continue
            href = ""
            for a in tds[0].find_all("a", href=True):
                if a["href"].startswith("http") and "wikipedia.org" not in a["href"]:
                    href = a["href"]
                    break
            urls.append(href)
        out.append((df, urls, heading))
    return out


def rows_from_table(df: pd.DataFrame, urls: list[str], race: config.Race, page_url: str,
                    heading: str = "") -> list[dict]:
    cols = [str(c) for c in df.columns]
    poll_col = next(c for c in cols if re.search(r"poll|source|pollster|firm", c, re.I))
    date_col = next(c for c in cols if re.search(r"date", c, re.I))
    sample_col = next((c for c in cols if re.search(r"sample", c, re.I)), None)
    cand_map = {c: match_candidate(c, race) for c in cols if match_candidate(c, race)}
    # Wikipedia omits the year inside month sections ("October 24–26" under "October 2026")
    default_year = _heading_year(heading) or date.today().year
    rows: list[dict] = []
    for i, r in df.iterrows():
        pollster_raw = str(r[poll_col])
        if not pollster_raw or pollster_raw.lower() in ("nan", poll_col.lower()):
            continue
        start, end = parse_date_range(r[date_col], default_year)
        if end is None or end > date.today():
            log.debug("skip row (date): %s | %s", pollster_raw, r[date_col])
            continue
        n, pop = parse_sample(r[sample_col]) if sample_col else (None, "")
        sponsor = ""
        pollster = canonical_pollster(re.split(r"/| for ", re.sub(r"\[.*?\]", "", pollster_raw))[0])
        if "/" in pollster_raw:
            sponsor = re.sub(r"\[.*?\]", "", pollster_raw.split("/", 1)[1]).strip()
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
    for df, urls, heading in tables_for_race(html, race):
        rows.extend(rows_from_table(df, urls, race, page_url, heading))
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
