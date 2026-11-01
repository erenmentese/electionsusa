"""Dependency-free SVG charts. Everything is rendered server-side so pages
work without JavaScript and are indexable. Charts scale via viewBox."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

W, H = 860, 360
PAD_L, PAD_R, PAD_T, PAD_B = 50, 165, 18, 36
FONT = "font-family='Inter, system-ui, -apple-system, Segoe UI, sans-serif'"


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    span = max(hi - lo, 1e-9)
    raw = span / n
    mag = 10 ** int(f"{raw:e}".split("e")[1])
    step = min((s for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=10) * mag
    start = (lo // step) * step
    ticks = []
    t = start
    while t <= hi + 1e-9:
        if t >= lo - 1e-9:
            ticks.append(round(t, 6))
        t += step
    return ticks


TICK_STEPS = (1, 3, 6, 12)  # months; each divides the next, so the ticks kept on phones are a subset
MIN_GAP, MIN_GAP_PHONE = 56, 100  # user units between date labels; phones draw them ~1.8x larger (see style.css)


def _date_ticks(d0: date, d1: date, width: float) -> list[tuple[date, str, bool]]:
    """January-aligned month ticks as (date, label, shown on phones).

    January is labelled with its year and other months with their abbreviation, so
    labels stay short ("Oct 2025  2026  Apr  Jul"); the first tick also carries its year.
    """
    per_month = width * 30.44 / max((d1 - d0).days, 1)
    step = next((s for s in TICK_STEPS if s * per_month >= MIN_GAP), 12)
    phone_step = next((s for s in TICK_STEPS if s * per_month >= MIN_GAP_PHONE), 12)
    ticks: list[tuple[date, str, bool]] = []
    y, m = (d0.year, d0.month) if d0.day == 1 else (d0.year + d0.month // 12, d0.month % 12 + 1)
    while (d := date(y, m, 1)) <= d1:
        if (m - 1) % step == 0:
            label = str(y) if m == 1 else d.strftime("%b %Y") if not ticks else d.strftime("%b")
            ticks.append((d, label, (m - 1) % phone_step == 0))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return ticks


def line_chart(series: dict[str, list[tuple[date, float]]], points: dict[str, list[tuple[date, float]]],
               colors: dict[str, str], title: str = "", y_label: str = "%", y_min: float | None = None,
               y_max: float | None = None, chart_id: str = "chart", short: dict[str, str] | None = None) -> str:
    all_vals = [v for s in series.values() for _, v in s] + [v for s in points.values() for _, v in s]
    all_dates = [d for s in series.values() for d, _ in s] + [d for s in points.values() for d, _ in s]
    if not all_vals or not all_dates:
        return empty_chart("Not enough polls yet to draw a trend.")
    lo = y_min if y_min is not None else max(0, min(all_vals) - 4)
    hi = y_max if y_max is not None else min(100, max(all_vals) + 4)
    if hi - lo < 8:
        mid = (hi + lo) / 2
        lo, hi = max(0, mid - 4), min(100, mid + 4)
    # the chart starts where the average does; older polls stay in the table below it
    start = min((s[0][0] for s in series.values() if s), default=None)
    if start:
        points = {c: [(d, v) for d, v in pts if d >= start] for c, pts in points.items()}
        all_vals = [v for s in series.values() for _, v in s] + [v for s in points.values() for _, v in s]
        all_dates = [d for s in series.values() for d, _ in s] + [d for s in points.values() for d, _ in s]
        lo = y_min if y_min is not None else max(0, min(all_vals) - 4)
        hi = y_max if y_max is not None else min(100, max(all_vals) + 4)
        if hi - lo < 8:
            mid = (hi + lo) / 2
            lo, hi = max(0, mid - 4), min(100, mid + 4)
    d0, d1 = min(all_dates), max(all_dates)
    if d0 == d1:
        d0 = d1 - timedelta(days=30)
    d1 = d1 + timedelta(days=max(3, (d1 - d0).days // 40))
    pw, ph = W - PAD_L - PAD_R, H - PAD_T - PAD_B

    def x(d: date) -> float:
        return PAD_L + pw * ((d - d0).days / max((d1 - d0).days, 1))

    def y(v: float) -> float:
        return PAD_T + ph * (1 - (v - lo) / (hi - lo))

    out = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-labelledby='{chart_id}-t' class='chart' {FONT}>",
           f"<title id='{chart_id}-t'>{escape(title)}</title>"]
    for t in _nice_ticks(lo, hi):
        yy = y(t)
        out.append(f"<line x1='{PAD_L}' x2='{W - PAD_R}' y1='{yy:.1f}' y2='{yy:.1f}' class='grid'/>")
        out.append(f"<text x='{PAD_L - 8}' y='{yy + 4:.1f}' text-anchor='end' class='tick y'>{t:g}{y_label}</text>")
    ticks = _date_ticks(d0, d1, pw)
    phone = [i for i, t in enumerate(ticks) if t[2]]
    if len(phone) > 1 and ticks[phone[0]][0].month != 1 and ticks[phone[1]][0].month == 1 \
            and x(ticks[phone[1]][0]) - x(ticks[phone[0]][0]) < 160:
        phone = phone[1:]  # too tight for "Oct 2025" beside "2026" on a phone; the year label is enough
    for i, (d, label, _) in enumerate(ticks):
        xx = x(d)
        anchor = "start" if xx - PAD_L < 30 else "middle"
        tick = f"<text x='{xx:.1f}' y='{H - 10}' text-anchor='{anchor}' class='tick{{}}'>{{}}</text>"
        if phone and i == phone[0] and i > 0 and d.month != 1:
            # the first label a phone shows needs its year too
            out.append(tick.format(" m-hide", label) + tick.format(" m-only", d.strftime("%b %Y")))
        else:
            out.append(tick.format("" if i in phone else " m-hide", label))
    # points first (behind lines)
    for name, pts in points.items():
        c = colors.get(name, "#6b7280")
        for d, v in pts:
            out.append(f"<circle cx='{x(d):.1f}' cy='{y(v):.1f}' r='3.2' fill='{c}' fill-opacity='0.35'/>")
    # lines + end labels (on phones the end labels are cropped off and the legend names the lines)
    labels, legend = [], []
    for name, s in series.items():
        if not s:
            continue
        c = colors.get(name, "#6b7280")
        path = " ".join(f"{'M' if i == 0 else 'L'}{x(d):.1f},{y(v):.1f}" for i, (d, v) in enumerate(s))
        out.append(f"<path d='{path}' fill='none' stroke='{c}' stroke-width='2.2' stroke-linejoin='round'/>")
        ld, lv = s[-1]
        labels.append((y(lv), c, f"{(short or {}).get(name, name)} {lv:.1f}{y_label}", x(ld)))
        legend.append((lv, c, (short or {}).get(name, name)))
    # de-overlap labels
    labels.sort()
    last = -99
    for yy, c, text, xx in labels:
        yy = max(yy, last + 14)
        last = yy
        out.append(f"<text x='{W - PAD_R + 8}' y='{yy + 4:.1f}' fill='{c}' class='label'>{escape(text)}</text>")
    out.append("</svg>")
    items = "".join(f"<li><i style='background:{c}'></i>{escape(n)} <b>{v:.1f}{y_label}</b></li>"
                    for v, c, n in sorted(legend, key=lambda t: -t[0]))
    crop = 100 * W / (W - PAD_R + 12)
    return f"<div class='trend-fig' style='--crop:{crop:.1f}%'>{''.join(out)}<ul class='trend-legend'>{items}</ul></div>"


def bar_chart(values: dict[str, float], colors: dict[str, str], title: str = "", chart_id: str = "bars",
              max_value: float | None = None) -> str:
    items = sorted(values.items(), key=lambda kv: -kv[1])
    if not items:
        return empty_chart("No polling average yet.")
    row_h, pad_l, pad_r = 30, 190, 70
    h = 16 + row_h * len(items)
    mx = max_value or max(v for _, v in items) * 1.15
    pw = W - pad_l - pad_r
    out = [f"<svg viewBox='0 0 {W} {h}' role='img' aria-labelledby='{chart_id}-t' class='chart bars' {FONT}>",
           f"<title id='{chart_id}-t'>{escape(title)}</title>"]
    for i, (name, v) in enumerate(items):
        yy = 8 + i * row_h
        c = colors.get(name, "#6b7280")
        bw = pw * (v / mx)
        out.append(f"<text x='{pad_l - 10}' y='{yy + 21}' text-anchor='end' class='label'>{escape(name)}</text>")
        out.append(f"<rect x='{pad_l}' y='{yy + 8}' width='{bw:.1f}' height='16' rx='2' fill='{c}'/>")
        out.append(f"<text x='{pad_l + bw + 8:.1f}' y='{yy + 22}' class='label strong'>{v:.1f}%</text>")
    out.append("</svg>")
    return "".join(out)


def grouped_bars(groups: dict[str, dict[str, float]], series_colors: dict[str, str], title: str = "",
                 chart_id: str = "grouped") -> str:
    """groups: outcome -> {series_name: value}. Used for polls-vs-markets."""
    if not groups:
        return empty_chart("No comparable data yet.")
    names = list(series_colors)
    row_h, pad_l, pad_r = 18 * len(names) + 14, 190, 70
    h = 16 + row_h * len(groups)
    mx = max((v for g in groups.values() for v in g.values()), default=1) * 1.15
    pw = W - pad_l - pad_r
    out = [f"<svg viewBox='0 0 {W} {h}' role='img' aria-labelledby='{chart_id}-t' class='chart bars' {FONT}>",
           f"<title id='{chart_id}-t'>{escape(title)}</title>"]
    for i, (outcome, vals) in enumerate(groups.items()):
        yy = 8 + i * row_h
        out.append(f"<text x='{pad_l - 10}' y='{yy + row_h / 2 + 4:.1f}' text-anchor='end' class='label'>{escape(outcome)}</text>")
        for j, s in enumerate(names):
            v = vals.get(s)
            by = yy + 4 + j * 18
            if v is None:
                out.append(f"<text x='{pad_l + 4}' y='{by + 12}' class='tick'>n/a</text>")
                continue
            bw = pw * (v / mx)
            out.append(f"<rect x='{pad_l}' y='{by}' width='{bw:.1f}' height='14' rx='3' fill='{series_colors[s]}'/>")
            out.append(f"<text x='{pad_l + bw + 6:.1f}' y='{by + 11}' class='tick'>{s} {v:.1f}%</text>")
    out.append("</svg>")
    return "".join(out)


def margin_columns(state: list[tuple[int, float]], nation: list[tuple[int, float]], colors: dict[str, str],
                   title: str = "", chart_id: str = "margins") -> str:
    """One column per election: the state's margin (Republican up, Democratic down), with the
    national margin as a line so the state's lean against the country is visible at a glance."""
    if not state:
        return empty_chart("No results.")
    h, pad_l, pad_r, pad_t, pad_b = 330, 52, 16, 14, 48
    top = max(abs(m) for _, m in state + nation)
    lim = next((t for t in (5, 10, 15, 20, 30, 40, 50, 60, 80, 100) if t >= top * 1.12), 100)
    step = (W - pad_l - pad_r) / len(state)
    ph = h - pad_t - pad_b

    def y(m: float) -> float:
        return pad_t + ph * (1 - (m + lim) / (2 * lim))

    def lean(m: float, fmt: str = ".1f") -> str:
        return "EVEN" if abs(m) < 0.05 else f"{'R' if m > 0 else 'D'}+{abs(m):{fmt}}"

    out = [f"<svg viewBox='0 0 {W} {h}' role='img' aria-labelledby='{chart_id}-t' class='chart' {FONT}>",
           f"<title id='{chart_id}-t'>{escape(title)}</title>"]
    for t in (-lim, -lim / 2, 0, lim / 2, lim):
        out.append(f"<line x1='{pad_l}' x2='{W - pad_r}' y1='{y(t):.1f}' y2='{y(t):.1f}' class='{'axis' if t == 0 else 'grid'}'/>")
        out.append(f"<text x='{pad_l - 8}' y='{y(t) + 4:.1f}' text-anchor='end' class='tick'>{lean(t, 'g')}</text>")
    for i, (yr, m) in enumerate(state):
        cx = pad_l + step * (i + 0.5)
        bw = step * 0.56
        y0, y1 = sorted((y(0), y(m)))
        c = colors["REP" if m > 0 else "DEM"]
        out.append(f"<rect x='{cx - bw / 2:.1f}' y='{y0:.1f}' width='{bw:.1f}' height='{max(y1 - y0, 1):.1f}' rx='2' "
                   f"fill='{c}'><title>{yr}: {escape(lean(m))}</title></rect>")
        # values sit in their own row above the years, where the national line can't cross them
        out.append(f"<text x='{cx:.1f}' y='{h - 26}' text-anchor='middle' class='label' style='fill:{c}'>{escape(lean(m))}</text>")
        out.append(f"<text x='{cx:.1f}' y='{h - 8}' text-anchor='middle' class='tick'>{yr}</text>")
    if nation:
        xs = {yr: pad_l + step * (i + 0.5) for i, (yr, _) in enumerate(state)}
        pts = [(xs[yr], y(m)) for yr, m in nation if yr in xs]
        out.append("<path d='" + " ".join(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}" for i, (px, py) in enumerate(pts))
                   + "' class='nat'/>")
        out += [f"<circle cx='{px:.1f}' cy='{py:.1f}' r='3' class='nat-dot'/>" for px, py in pts]
    out.append("</svg>")
    return "".join(out)


def empty_chart(msg: str) -> str:
    return (f"<svg viewBox='0 0 {W} 120' class='chart empty' {FONT}>"
            f"<text x='{W / 2}' y='64' text-anchor='middle' class='label'>{escape(msg)}</text></svg>")
