"""Dependency-free SVG charts. Everything is rendered server-side so pages
work without JavaScript and are indexable. Charts scale via viewBox."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

W, H = 860, 360
PAD_L, PAD_R, PAD_T, PAD_B = 46, 150, 18, 36
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


def _month_ticks(d0: date, d1: date) -> list[date]:
    ticks = []
    y, m = d0.year, d0.month
    span_days = (d1 - d0).days
    step = 1 if span_days <= 240 else 2 if span_days <= 500 else 3
    d = date(y, m, 1)
    if d < d0:
        m += 1
        if m > 12:
            m, y = 1, y + 1
        d = date(y, m, 1)
    while d <= d1:
        ticks.append(d)
        m += step
        while m > 12:
            m, y = m - 12, y + 1
        d = date(y, m, 1)
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
        out.append(f"<text x='{PAD_L - 8}' y='{yy + 4:.1f}' text-anchor='end' class='tick'>{t:g}{y_label}</text>")
    for d in _month_ticks(d0, d1):
        xx = x(d)
        label = d.strftime("%b %Y") if d.month in (1,) or (d1 - d0).days > 400 else d.strftime("%b")
        out.append(f"<text x='{xx:.1f}' y='{H - 10}' text-anchor='middle' class='tick'>{label}</text>")
    # points first (behind lines)
    for name, pts in points.items():
        c = colors.get(name, "#6b7280")
        for d, v in pts:
            out.append(f"<circle cx='{x(d):.1f}' cy='{y(v):.1f}' r='3.2' fill='{c}' fill-opacity='0.35'/>")
    # lines + end labels
    labels = []
    for name, s in series.items():
        if not s:
            continue
        c = colors.get(name, "#6b7280")
        path = " ".join(f"{'M' if i == 0 else 'L'}{x(d):.1f},{y(v):.1f}" for i, (d, v) in enumerate(s))
        out.append(f"<path d='{path}' fill='none' stroke='{c}' stroke-width='2.2' stroke-linejoin='round'/>")
        ld, lv = s[-1]
        labels.append((y(lv), c, f"{(short or {}).get(name, name)} {lv:.1f}{y_label}", x(ld)))
    # de-overlap labels
    labels.sort()
    last = -99
    for yy, c, text, xx in labels:
        yy = max(yy, last + 14)
        last = yy
        out.append(f"<text x='{W - PAD_R + 8}' y='{yy + 4:.1f}' fill='{c}' class='label'>{escape(text)}</text>")
    out.append("</svg>")
    return "".join(out)


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


def empty_chart(msg: str) -> str:
    return (f"<svg viewBox='0 0 {W} 120' class='chart empty' {FONT}>"
            f"<text x='{W / 2}' y='64' text-anchor='middle' class='label'>{escape(msg)}</text></svg>")
