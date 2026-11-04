# Daily PnL explain, 2025-10-31 → 2026-10-29 (254 days)

**Synthetic market**: quotes reconstructed from the ECB and noised (0.2 to 0.5 bp), EURIBOR 6M fixings reconstructed (DEPOSIT 6M quote of the day). The fixings component is built by assumption. This result validates the decomposition mechanics, not market behaviour.

| Component | Mean (EUR) | Mean absolute value (EUR) | Max absolute (EUR) |
|---|---:|---:|---:|
| total | 1,404 | 110,972 | 478,072 |
| carry | 367 | 385 | 1,510 |
| fixings | 0 | 2 | 163 |
| delta | -2,819 | 110,920 | 473,019 |
| gamma | -465 | 465 | 9,668 |
| residual | 4,319 | 5,468 | 62,247 |

- Mean absolute residual: 4.93% of the mean absolute PnL; day-by-day median of |residual| / |PnL|: 3.15%; explained variance 1 − var(residual) / var(PnL): 99.6345%.
- Worst day: 2026-05-04 (residual 62,247 EUR, PnL 244,111 EUR).
- **Source of the residual**: the non-differentiability of Hagan-West. Its monotone convex scheme changes region when quotes move, V is not smooth and the first-order expansion breaks down (on 2026-08-06, the slope along the path q_c → q1 goes from −54,610 to +9,128 EUR for a move of about 1 bp). Log-linear twin, same days: mean |residual| 289 EUR, max 5,366 EUR (0.26% of the mean absolute PnL).
- Fixing days (non-zero component): 7.
- 10Y IRS basis jump (+2.5 bp from 2026-05-04, 5 days): max |residual| 62,247 EUR on those days. An isolated move of one quote pushes the Hagan-West curve out of its region, hence the worst day of the year.
- Run time: 977 s for 254 days (3.8 s per day, Hagan-West, five curve builds per day).

Full series: [`pnl_series.csv`](pnl_series.csv).
