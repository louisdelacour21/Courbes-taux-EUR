"""Morning briefing of the portfolio: value, DV01, top 3 pillars, explained PnL of the previous day, alerts, run time.

    python -m ratecurves.briefing [YYYY-MM-DD]
"""
import sys
import time
from datetime import date

import numpy as np

from ratecurves import pnl
from ratecurves import pricing as p
from ratecurves import quotes as c
from ratecurves import risk as r
from ratecurves.curves import CurveHW

RESIDUAL_THRESHOLD = 0.10  # share of the previous day's PnL
RESIDUAL_THRESHOLD_EUR = 10_000.0
ISOLATED_THRESHOLD_BP = 2.0  # gap between a quote's move and that of its neighbours (basis jump)


def eur(x: float) -> str:
    return f"{round(x):,}".replace(",", " ")  # integer: no "-0"


def briefing(day: date | None = None, cls=CurveHW) -> dict:
    t0 = time.perf_counter()
    quotes = c.read_quotes()
    days = sorted(quotes.date.unique())
    day = day or days[-1]
    prev_day = days[days.index(day) - 1]
    pf, fx = p.read_portfolio(), p.deposit_fixings(quotes)
    q0, q1 = c.of_day(quotes, prev_day), c.of_day(quotes, day)

    e, k = r.build(day, *q1, cls)
    v, b = r.buckets(pf, day, e, k, fx)
    names = r.labels(e, k)
    top = [(names[i], float(b[i])) for i in np.argsort(-np.abs(b))[:3]]
    expl = pnl.explain(pf, prev_day, day, q0, q1, fx, cls)

    alerts = []
    if abs(expl["residual"]) > max(RESIDUAL_THRESHOLD * abs(expl["total"]), RESIDUAL_THRESHOLD_EUR):
        alerts.append(f"previous-day residual {eur(expl['residual'])} EUR for a PnL of {eur(expl['total'])} EUR")
    for n, prefix in ((0, "OIS "), (1, "")):
        keys = list(q1[n])
        d = np.array([(q1[n][t] - q0[n][t]) * 100 for t in keys])
        neighbours = [np.mean([d[j] for j in (i - 1, i + 1) if 0 <= j < len(d)]) for i in range(len(d))]
        alerts += [f"{prefix}{t} moved {d[i]:+.1f} bp against {neighbours[i]:+.1f} bp for its neighbours"
                   for i, t in enumerate(keys) if abs(d[i] - neighbours[i]) > ISOLATED_THRESHOLD_BP]
    return {"day": day, "prev_day": prev_day, "value": v, "dv01": float(b.sum()), "top3": top, "pnl": expl,
            "alerts": alerts, "duration": time.perf_counter() - t0}


def text(s: dict) -> str:
    lines = [f"Briefing for {s['day']} (previous day {s['prev_day']}), Hagan-West, reconstructed quotes",
             f"Portfolio value: {eur(s['value'])} EUR; DV01 (sum of buckets): {eur(s['dv01'])} EUR/bp",
             "Top 3 pillars: " + "; ".join(f"{n} {eur(x)} EUR/bp" for n, x in s["top3"]),
             "Previous-day PnL: " + "; ".join(f"{k} {eur(x)}" for k, x in s["pnl"].items()) + " (EUR)",
             "Alerts: " + ("; ".join(s["alerts"]) if s["alerts"] else "none"),
             f"Run time: {s['duration']:.1f} s"]
    return "\n".join(lines)


if __name__ == "__main__":
    print(text(briefing(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)))
