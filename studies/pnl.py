"""Daily PnL explain of the portfolio (data/portfolio.csv) over the whole year of quotes, Hagan-West.

Synthetic market: reconstructed noisy quotes, reconstructed fixings. The study validates the decomposition
mechanics, not market behaviour.

    python studies/pnl.py   ->   studies/pnl.md, studies/pnl_series.csv
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ratecurves import pnl  # noqa: E402
from ratecurves import pricing as p  # noqa: E402
from ratecurves import quotes as c  # noqa: E402
from ratecurves.curves import Curve  # noqa: E402
from ratecurves.quotes import JUMP  # noqa: E402

COMPONENTS = ["carry", "fixings", "delta", "gamma", "residual"]
eur = lambda x: f"{x:,.0f}"  # noqa: E731


def main():
    quotes = c.read_quotes()
    days = sorted(quotes.date.unique())
    pf, fix = p.read_portfolio(), p.deposit_fixings(quotes)

    t0, rows, twin = time.perf_counter(), [], []
    for d0, d1 in zip(days, days[1:]):
        rows.append({"day": d1, **pnl.explain(pf, d0, d1, c.of_day(quotes, d0), c.of_day(quotes, d1), fix)})
    duration = time.perf_counter() - t0
    for d0, d1 in zip(days, days[1:]):  # log-linear twin: V smooth in the quotes
        twin.append(pnl.explain(pf, d0, d1, c.of_day(quotes, d0), c.of_day(quotes, d1), fix, Curve)["residual"])
    df = pd.DataFrame(rows)
    df.assign(residual_loglin=twin).round(2).to_csv(Path(__file__).with_name("pnl_series.csv"), index=False)
    ll = pd.Series(twin).abs()

    a = df[["total"] + COMPONENTS].abs()
    share = df.residual.abs() / df.total.abs()
    jump = df[df.day.isin([d for d in days if d >= JUMP["start"]][: JUMP["days"] + 1])]
    md = [f"# Daily PnL explain, {df.day.min()} → {df.day.max()} ({len(df)} days)", "",
          "**Synthetic market**: quotes reconstructed from the ECB and noised (0.2 to 0.5 bp), EURIBOR 6M fixings "
          "reconstructed (DEPOSIT 6M quote of the day). The fixings component is built by assumption. This result "
          "validates the decomposition mechanics, not market behaviour.", "",
          "| Component | Mean (EUR) | Mean absolute value (EUR) | Max absolute (EUR) |", "|---|---:|---:|---:|"]
    md += [f"| {k} | {eur(df[k].mean())} | {eur(a[k].mean())} | {eur(a[k].max())} |" for k in ["total"] + COMPONENTS]
    worst = a.residual.idxmax()
    md += ["", f"- Mean absolute residual: {a.residual.mean() / a.total.mean():.2%} of the mean absolute PnL; "
           f"day-by-day median of |residual| / |PnL|: {share.median():.2%}; "
           f"explained variance 1 − var(residual) / var(PnL): {1 - df.residual.var() / df.total.var():.4%}.",
           f"- Worst day: {df.day[worst]} (residual {eur(df.residual[worst])} EUR, PnL {eur(df.total[worst])} EUR).",
           "- **Source of the residual**: the non-differentiability of Hagan-West. Its monotone convex scheme changes "
           "region when quotes move, V is not smooth and the first-order expansion breaks down (on 2026-08-06, the "
           "slope along the path q_c → q1 goes from −54,610 to +9,128 EUR for a move of about 1 bp). Log-linear "
           f"twin, same days: mean |residual| {eur(ll.mean())} EUR, max {eur(ll.max())} EUR "
           f"({ll.mean() / a.total.mean():.2%} of the mean absolute PnL).",
           f"- Fixing days (non-zero component): {int((a.fixings > 0.5).sum())}.",
           f"- 10Y IRS basis jump (+{JUMP['bp']} bp from {JUMP['start']}, {JUMP['days']} days): max |residual| "
           f"{eur(jump.residual.abs().max())} EUR on those days. An isolated move of one quote pushes the Hagan-West "
           "curve out of its region, hence the worst day of the year.",
           f"- Run time: {duration:.0f} s for {len(df)} days ({duration / len(df):.1f} s per day, Hagan-West, "
           "five curve builds per day).", "",
           "Full series: [`pnl_series.csv`](pnl_series.csv)."]
    Path(__file__).with_suffix(".md").write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    print(Path(__file__).with_suffix(".md"))


if __name__ == "__main__":
    main()
