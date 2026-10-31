"""Presidential results by state, 1976-2024: the map, the /states/ pages and their facts.

Votes come from the MIT Election Data and Science Lab's state-level returns (CC0), which
compile the House Clerk's official statistics. Electoral votes come from the Census
Bureau's House apportionment (representatives + 2; DC has 3), plus the district splits in
Maine and Nebraska listed below. Electoral votes are counted as each state's result
pledged them; the handful of faithless electors (1976, 1988, 2000, 2004, 2016) are ignored.

Margins are signed Republican-positive throughout: +3.0 means R +3.0, -3.0 means D +3.0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from . import config

MEDSL = config.SEED_DIR / "medsl" / "1976-2024-president.csv"
APPORTIONMENT = config.SEED_DIR / "census" / "apportionment.csv"

# year -> ((Democratic nominee as printed in the MEDSL file, display name), (Republican ...))
NOMINEES = {
    1976: (("CARTER, JIMMY", "Jimmy Carter"), ("FORD, GERALD", "Gerald Ford")),
    1980: (("CARTER, JIMMY", "Jimmy Carter"), ("REAGAN, RONALD", "Ronald Reagan")),
    1984: (("MONDALE, WALTER", "Walter Mondale"), ("REAGAN, RONALD", "Ronald Reagan")),
    1988: (("DUKAKIS, MICHAEL", "Michael Dukakis"), ("BUSH, GEORGE H.W.", "George H.W. Bush")),
    1992: (("CLINTON, BILL", "Bill Clinton"), ("BUSH, GEORGE H.W.", "George H.W. Bush")),
    1996: (("CLINTON, BILL", "Bill Clinton"), ("DOLE, ROBERT", "Bob Dole")),
    2000: (("GORE, AL", "Al Gore"), ("BUSH, GEORGE W.", "George W. Bush")),
    2004: (("KERRY, JOHN", "John Kerry"), ("BUSH, GEORGE W.", "George W. Bush")),
    2008: (("OBAMA, BARACK H.", "Barack Obama"), ("MCCAIN, JOHN", "John McCain")),
    2012: (("OBAMA, BARACK H.", "Barack Obama"), ("ROMNEY, MITT", "Mitt Romney")),
    2016: (("CLINTON, HILLARY", "Hillary Clinton"), ("TRUMP, DONALD J.", "Donald Trump")),
    2020: (("BIDEN, JOSEPH R. JR", "Joe Biden"), ("TRUMP, DONALD J.", "Donald Trump")),
    2024: (("HARRIS, KAMALA D.", "Kamala Harris"), ("TRUMP, DONALD J.", "Donald Trump")),
}

# Maine (since 1972) and Nebraska (since 1992) award one elector per congressional district.
# Years in which a state's electors split: (Democratic EVs, Republican EVs, note)
SPLITS = {
    (2008, "NE"): (1, 4, "Nebraska's 2nd district (Omaha) voted for Barack Obama"),
    (2016, "ME"): (3, 1, "Maine's 2nd district voted for Donald Trump"),
    (2020, "ME"): (3, 1, "Maine's 2nd district voted for Donald Trump"),
    (2020, "NE"): (1, 4, "Nebraska's 2nd district (Omaha) voted for Joe Biden"),
    (2024, "ME"): (3, 1, "Maine's 2nd district voted for Donald Trump"),
    (2024, "NE"): (1, 4, "Nebraska's 2nd district (Omaha) voted for Kamala Harris"),
}

# MEDSL lines that are not a candidate: ballot options, write-in buckets and blank rows
NOT_A_CANDIDATE = ("OTHER", "NONE OF", "BLANK", "SCATTER", "WRITE", "VOID", "OVER", "UNDER")
NOTABLE_OTHER = 5.0  # a third-party candidate is named when they won at least this share


def short(name: str) -> str:
    """Last name for compact labels: "George H.W. Bush" -> "Bush"."""
    return name.split()[-1]


NAME_FIXES = {"Macbride": "MacBride", "Edward": "Ed"}  # Roger MacBride (1976), Ed Clark (1980)


def display_name(medsl: str) -> str:
    """ "MCMULLIN, EVAN" -> "Evan McMullin"; 'CLARK, EDWARD ""ED""' -> "Ed Clark"."""
    last, _, first = re.sub(r'"+[^"]*"+', "", medsl).partition(", ")
    first_words = first.split()
    suffix = [first_words.pop()] if first_words and first_words[-1].rstrip(".") in ("JR", "SR", "II", "III") else []
    words = []
    for w in first_words + last.split() + suffix:
        w = w.capitalize()
        if w.startswith("Mc") and len(w) > 2:
            w = "Mc" + w[2:].capitalize()
        words.append(NAME_FIXES.get(w, {"Jr": "Jr.", "Sr": "Sr.", "Ii": "II", "Iii": "III"}.get(w.rstrip("."), w)))
    return " ".join(words)


def fmt_margin(margin: float, dem: str, rep: str) -> str:
    """Signed R-positive margin as "Trump +1.7" / "Harris +6.9" / "Tie"."""
    if abs(margin) < 0.05:
        return "Tie"
    return f"{short(rep) if margin > 0 else short(dem)} +{abs(margin):.1f}"


def fmt_lean(margin: float) -> str:
    """Party-letter form of a margin: "R+1.7", "D+6.9", "EVEN"."""
    if abs(margin) < 0.05:
        return "EVEN"
    return f"{'R' if margin > 0 else 'D'}+{abs(margin):.1f}"


def electoral_votes_census(year: int) -> int:
    """Apportionment in force for an election: 1976 and 1980 use the 1970 census, 2024 and 2028 the 2020 one."""
    return 10 * ((year - 2) // 10)


@dataclass
class StateYear:
    year: int
    po: str
    dem: str                 # nominee display names
    rep: str
    dem_votes: int
    rep_votes: int
    total: int
    ev: int
    ev_dem: int
    ev_rep: int
    split_note: str = ""
    other: str = ""          # largest third-party candidate, when notable
    other_votes: int = 0

    @property
    def dem_pct(self) -> float:
        return 100 * self.dem_votes / self.total

    @property
    def rep_pct(self) -> float:
        return 100 * self.rep_votes / self.total

    @property
    def other_pct(self) -> float:
        return 100 - self.dem_pct - self.rep_pct

    @property
    def margin(self) -> float:
        return self.rep_pct - self.dem_pct

    @property
    def winner(self) -> str:
        return "R" if self.rep_votes > self.dem_votes else "D"

    @property
    def winner_name(self) -> str:
        return self.rep if self.winner == "R" else self.dem

    @property
    def loser_name(self) -> str:
        return self.dem if self.winner == "R" else self.rep

    @property
    def margin_label(self) -> str:
        return fmt_margin(self.margin, self.dem, self.rep)


@dataclass
class NationYear:
    year: int
    dem: str
    rep: str
    dem_votes: int = 0
    rep_votes: int = 0
    total: int = 0
    ev_dem: int = 0
    ev_rep: int = 0
    others: dict[str, int] = field(default_factory=dict)  # third-party votes by candidate

    @property
    def dem_pct(self) -> float:
        return 100 * self.dem_votes / self.total

    @property
    def rep_pct(self) -> float:
        return 100 * self.rep_votes / self.total

    @property
    def other_pct(self) -> float:
        return 100 - self.dem_pct - self.rep_pct

    @property
    def top_other(self) -> tuple[str, float] | None:
        """The leading third-party candidate nationally, when notable (Anderson 1980, Perot 1992/1996).
        The share is a floor: votes on unnamed lines (Perot in five states in 1996) aren't counted."""
        if not self.others:
            return None
        name = max(self.others, key=self.others.get)
        pct = 100 * self.others[name] / self.total
        return (name, pct) if pct >= NOTABLE_OTHER else None

    @property
    def margin(self) -> float:
        return self.rep_pct - self.dem_pct

    @property
    def winner(self) -> str:
        """The Electoral College winner (not the popular-vote winner, as in 2000 and 2016)."""
        return "R" if self.ev_rep > self.ev_dem else "D"

    @property
    def winner_name(self) -> str:
        return self.rep if self.winner == "R" else self.dem


@dataclass
class StateHistory:
    po: str
    name: str
    fips: str
    years: list[StateYear] = field(default_factory=list)  # oldest first

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "-")

    @property
    def path(self) -> str:
        return f"/states/{self.slug}/"

    @property
    def latest(self) -> StateYear:
        return self.years[-1]

    def by_year(self, year: int) -> StateYear | None:
        return next((y for y in self.years if y.year == year), None)

    def lean(self, nation: dict[int, NationYear], year: int | None = None) -> float:
        """State margin minus national margin: how much redder (+) or bluer (-) than the country."""
        sy = self.by_year(year) if year else self.latest
        return sy.margin - nation[sy.year].margin

    def picked_winner(self, nation: dict[int, NationYear]) -> int:
        return sum(1 for y in self.years if y.winner == nation[y.year].winner)

    def last_win(self, party: str) -> int | None:
        return next((y.year for y in reversed(self.years) if y.winner == party), None)

    def streak(self) -> int:
        """Consecutive elections, up to the latest, won by the latest winner's party."""
        n = 0
        for y in reversed(self.years):
            if y.winner != self.latest.winner:
                break
            n += 1
        return n


def _state_name(medsl_upper: str) -> str:
    return " ".join(w if w == "of" else w.capitalize() for w in medsl_upper.lower().split())


def load() -> tuple[dict[str, StateHistory], dict[int, NationYear]]:
    """Every state's results (keyed by postal code, alphabetical by name) and the national totals."""
    df = pd.read_csv(MEDSL)
    ap = pd.read_csv(APPORTIONMENT)
    ap = ap[ap["Geography Type"] == "State"]
    reps = {(r["Name"], int(r["Year"])): int(r["Number of Representatives"])
            for _, r in ap.iterrows() if pd.notna(r["Number of Representatives"])}

    states: dict[str, StateHistory] = {}
    nation = {y: NationYear(y, d[1], r[1]) for y, (d, r) in NOMINEES.items()}
    for (year, po), g in df[df["year"].isin(list(NOMINEES))].groupby(["year", "state_po"]):
        year = int(year)
        (d_key, d_name), (r_key, r_name) = NOMINEES[year]
        name = _state_name(g["state"].iat[0])
        st = states.setdefault(po, StateHistory(po=po, name=name, fips=f"{int(g['state_fips'].iat[0]):02d}"))
        # a candidate can appear on several party lines (e.g. New York): sum them
        votes = g.groupby(g["candidate"].fillna(""))["candidatevotes"].sum()
        dem_votes, rep_votes = int(votes.get(d_key, 0)), int(votes.get(r_key, 0))
        total = int(g["totalvotes"].iat[0])
        ev = 3 if po == "DC" else reps[(name, electoral_votes_census(year))] + 2
        if (year, po) in SPLITS:
            ev_dem, ev_rep, note = SPLITS[(year, po)]
        else:
            ev_dem, ev_rep, note = (ev, 0, "") if dem_votes > rep_votes else (0, ev, "")
        others = votes.drop([d_key, r_key], errors="ignore")
        others = others[[bool(c) and not any(k in c for k in NOT_A_CANDIDATE) for c in others.index]]
        other, other_votes = "", 0
        if len(others) and 100 * others.max() / total >= NOTABLE_OTHER:
            other, other_votes = display_name(others.idxmax()), int(others.max())
        st.years.append(StateYear(year, po, d_name, r_name, dem_votes, rep_votes, total, ev, ev_dem, ev_rep,
                                  note, other, other_votes))
        n = nation[year]
        for cand, v in others.items():
            n.others[display_name(cand)] = n.others.get(display_name(cand), 0) + int(v)
        n.dem_votes += dem_votes
        n.rep_votes += rep_votes
        n.total += total
        n.ev_dem += ev_dem
        n.ev_rep += ev_rep
    for st in states.values():
        st.years.sort(key=lambda y: y.year)
    return dict(sorted(states.items(), key=lambda kv: kv[1].name)), nation


def national_sentence(states: dict[str, StateHistory], nation: dict[int, NationYear], year: int) -> str:
    n = nation[year]
    won, lost = (n.rep, n.dem) if n.winner == "R" else (n.dem, n.rep)
    ev_won, ev_lost = (n.ev_rep, n.ev_dem) if n.winner == "R" else (n.ev_dem, n.ev_rep)
    carried = sum(1 for st in states.values() if st.po != "DC" and st.by_year(year).winner == n.winner)
    popular = n.rep if n.rep_votes > n.dem_votes else n.dem
    also = " also" if popular == won else ""
    hi, lo = max(n.dem_pct, n.rep_pct), min(n.dem_pct, n.rep_pct)
    # The total third-party share is exact; one candidate's national share isn't always (in 1996
    # five states report Perot only inside an unnamed "independent" line), so name the leader only.
    third = f" Other candidates won {n.other_pct:.1f}%, led by {n.top_other[0]}." if n.top_other else ""
    return (f"{won} won the {year} presidential election with {ev_won} electoral votes to {lost}'s {ev_lost}, "
            f"carrying {carried} of the 50 states. {short(popular)}{also} won the national popular vote, {hi:.1f}% to {lo:.1f}%.{third}")


def answer_sentence(st: StateHistory, nation: dict[int, NationYear]) -> str:
    """Dated, quotable summary of a state's latest result: the page lead and its meta description."""
    y = st.latest
    hi, lo = max(y.dem_pct, y.rep_pct), min(y.dem_pct, y.rep_pct)
    if y.split_note:
        evs = f"its {y.ev} electoral votes split {max(y.ev_dem, y.ev_rep)}–{min(y.ev_dem, y.ev_rep)} ({y.split_note})"
    else:
        evs = f"all {y.ev} of its electoral votes went to {short(y.winner_name)}"
    picked = st.picked_winner(nation)
    who = "The District of Columbia" if st.po == "DC" else st.name
    return (f"{who} voted for {y.winner_name} in {y.year}, {hi:.1f}% to {lo:.1f}% ({y.margin_label}); {evs}. "
            f"It has backed the winning candidate in {picked} of the last {len(st.years)} presidential elections.")
