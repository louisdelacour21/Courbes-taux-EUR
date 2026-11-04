"""Risk of the swap portfolio (data/portfolio.csv) on the last quote day, Hagan-West and log-linear:
value, DV01, buckets, hedging, IRRBB, bucket locality; shock export for project 04.

    python studies/risk.py   ->   studies/risk.md, studies/irrbb_shocks.yaml
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ratecurves import pricing as p  # noqa: E402
from ratecurves import quotes as c  # noqa: E402
from ratecurves import risk as r  # noqa: E402
from ratecurves.curves import Curve, CurveHW  # noqa: E402


def eur(v):
    return f"{v:,.0f}"


def main():
    quotes = c.read_quotes()
    day = quotes.date.max()
    ois, six = c.of_day(quotes, day)
    fx, pf = p.deposit_fixings(quotes), p.read_portfolio()
    off_grid = [s for s in pf if s.name == "P10Y-2024"]

    res = {}
    for name, K in [("Hagan-West", CurveHW), ("Log-linear", Curve)]:
        e, k = r.build(day, ois, six, K)
        t0 = time.perf_counter()
        v, b = r.buckets(pf, day, e, k, fx)
        tb = time.perf_counter() - t0
        bump = [r.value(pf, day, *r.build(day, {t: x + d for t, x in ois.items()},
                                          {t: x + d for t, x in six.items()}, K), fx) for d in (0.01, -0.01)]
        h, B = r.hedge(day, e, k, b)
        res[name] = dict(v=v, b=b, tb=tb, dv01_q=(bump[0] - bump[1]) / 2, dv01_z=r.dv01_zero(pf, day, e, k, fx),
                         h=h, residual=np.abs(b + B @ h).max(), irrbb=r.irrbb(pf, day, e, k, fx),
                         b10=r.buckets(off_grid, day, e, k, fx)[1], lab=r.labels(e, k))
    lab = res["Hagan-West"]["lab"]
    hw, ll = res["Hagan-West"], res["Log-linear"]

    md = [f"# Risk of the swap portfolio on {day}", "",
          "Ten swaps (payers and receivers, forward starts, seasoned swaps with a past fixing), "
          "`data/portfolio.csv`. Past EURIBOR 6M fixings: reconstructed DEPOSIT 6M quote of the fixing day "
          "(assumption, see `assumptions.md`).", "",
          "| Measure | Hagan-West | Log-linear |", "|---|---:|---:|",
          f"| Value (EUR) | {eur(hw['v'])} | {eur(ll['v'])} |",
          f"| Quote DV01, ±1 bp rebootstrap (EUR/bp) | {eur(hw['dv01_q'])} | {eur(ll['dv01_q'])} |",
          f"| Σ buckets (EUR/bp) | {eur(hw['b'].sum())} | {eur(ll['b'].sum())} |",
          f"| Zero DV01, +1 bp on zero rates (EUR/bp) | {eur(hw['dv01_z'])} | {eur(ll['dv01_z'])} |",
          f"| Bucket run time (s) | {hw['tb']:.2f} | {ll['tb']:.2f} |",
          f"| Max hedge residual (EUR/bp) | {hw['residual']:.1e} | {ll['residual']:.1e} |", "",
          "Quote DV01 and zero DV01 differ (~4%): one bp on the quotes does not shift the zeros by one bp "
          "(annuity against zero duration, and the €STR/6M basis moves with it).", "",
          "## Buckets and hedge (Hagan-West)", "",
          "Hedge in calibration instruments at par, fixed-rate payer notional (negative = receiver). "
          "Instruments with |bucket| > 100 EUR/bp:", "",
          "| Instrument | Bucket (EUR/bp) | Hedge notional (EUR) |", "|---|---:|---:|"]
    md += [f"| {lab[i]} | {hw['b'][i]:,.0f} | {eur(hw['h'][i])} |"
           for i in np.argsort(-np.abs(hw["b"])) if abs(hw["b"][i]) > 100]

    md += ["", "## IRRBB, ΔEVE (BCBS 2016, EUR, EBA floor)", "", "| Scenario | Hagan-West | Log-linear |",
           "|---|---:|---:|"]
    md += [f"| {s} | {eur(hw['irrbb'][s])} | {eur(ll['irrbb'][s])} |" for s in r.SCENARIOS]
    worst = min(hw["irrbb"], key=hw["irrbb"].get)
    md += ["", f"Worst scenario: {worst} ({eur(hw['irrbb'][worst])} EUR). Shocks exported for project 04 in "
           "`studies/irrbb_shocks.yaml` (bp per maturity, before the floor)."]

    md += ["", "## Bucket locality: swap P10Y-2024 alone (payer, EUR 25m, 2.80%, maturity 2034-03-15)", "",
           "A spot swap of quoted tenor (P10Y) has its dates on the pillars: its buckets are identical under both "
           "interpolations (IRS 10Y + OIS). P10Y-2024 has its dates between pillars, so the interpolation matters.", "",
           "| Instrument | Hagan-West | Log-linear |", "|---|---:|---:|"]
    i10 = [lab.index("IRS 7Y"), lab.index("IRS 8Y")]  # pillars around 2034-03-15
    for i in range(len(lab)):
        if max(abs(hw["b10"][i]), abs(ll["b10"][i])) > 1:
            md.append(f"| {lab[i]} | {hw['b10'][i]:,.1f} | {ll['b10'][i]:,.1f} |")
    outside = {n: 1 - np.abs(x["b10"][i10]).sum() / np.abs(x["b10"]).sum() for n, x in res.items()}
    active = {n: int((np.abs(x["b10"]) > 1).sum()) for n, x in res.items()}
    md += ["", f"Share of |buckets| outside IRS 7Y and 8Y: Hagan-West {outside['Hagan-West']:.1%}, log-linear "
           f"{outside['Log-linear']:.1%}; instruments above 1 EUR/bp: {active['Hagan-West']} against "
           f"{active['Log-linear']}."]

    out = Path(__file__).parent
    (out / "irrbb_shocks.yaml").write_bytes(r.shocks_yaml().encode("utf-8"))
    (out / "risk.md").write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    print(out / "risk.md")


if __name__ == "__main__":
    main()
