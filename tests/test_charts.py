from datetime import date

from pipeline import charts

PLOT_W = charts.W - charts.PAD_L - charts.PAD_R


def labels(d0, d1):
    return [(label, phone) for _, label, phone in charts._date_ticks(d0, d1, PLOT_W)]


def test_date_ticks_stay_short_and_thin_out_on_phones():
    # a 13-month trend: quarterly on both, years only on January, the first tick dated
    assert labels(date(2025, 9, 26), date(2026, 11, 10)) == [
        ("Oct 2025", True), ("2026", True), ("Apr", True), ("Jul", True), ("Oct", True)]
    # 8 months: monthly on desktop, quarterly on phones
    assert labels(date(2026, 3, 15), date(2026, 11, 5)) == [
        ("Apr 2026", True), ("May", False), ("Jun", False), ("Jul", True), ("Aug", False), ("Sep", False),
        ("Oct", True), ("Nov", False)]


def test_trend_chart_markup():
    s = [(date(2025, 10, 1), 45.0), (date(2026, 10, 31), 48.0)]
    html = charts.line_chart({"Democrats": s, "Republicans": [(d, v - 5) for d, v in s]},
                             {"Democrats": [(date(2024, 3, 1), 40.0), (date(2026, 5, 1), 47.0)]},
                             {"Democrats": "#1d4ed8", "Republicans": "#b91c1c"})
    assert html.startswith("<div class='trend-fig' style='--crop:")
    assert html.count("<circle") == 1  # polls from before the average starts are left off the chart
    assert "<li><i style='background:#1d4ed8'></i>Democrats <b>48.0%</b></li>" in html  # phone legend
    assert "class='tick'>2026</text>" in html
