# Risk of the swap portfolio on 2026-10-29

Ten swaps (payers and receivers, forward starts, seasoned swaps with a past fixing), `data/portfolio.csv`. Past EURIBOR 6M fixings: reconstructed DEPOSIT 6M quote of the fixing day (assumption, see `assumptions.md`).

| Measure | Hagan-West | Log-linear |
|---|---:|---:|
| Value (EUR) | 2,392,338 | 2,403,363 |
| Quote DV01, ±1 bp rebootstrap (EUR/bp) | 36,256 | 36,202 |
| Σ buckets (EUR/bp) | 36,256 | 36,202 |
| Zero DV01, +1 bp on zero rates (EUR/bp) | 37,593 | 37,590 |
| Bucket run time (s) | 0.59 | 0.20 |
| Max hedge residual (EUR/bp) | 1.8e-12 | 4.5e-13 |

Quote DV01 and zero DV01 differ (~4%): one bp on the quotes does not shift the zeros by one bp (annuity against zero duration, and the €STR/6M basis moves with it).

## Buckets and hedge (Hagan-West)

Hedge in calibration instruments at par, fixed-rate payer notional (negative = receiver). Instruments with |bucket| > 100 EUR/bp:

| Instrument | Bucket (EUR/bp) | Hedge notional (EUR) |
|---|---:|---:|
| IRS 10Y | 42,182 | -50,133,703 |
| IRS 6Y | 21,440 | -39,776,038 |
| IRS 3Y | -18,227 | 64,539,777 |
| IRS 30Y | 18,153 | -10,000,022 |
| IRS 8Y | 15,597 | -22,416,108 |
| IRS 5Y | -12,476 | 27,325,610 |
| IRS 12Y | -10,733 | 10,999,803 |
| IRS 4Y | -9,619 | 25,907,706 |
| IRS 15Y | 6,502 | -5,610,761 |
| IRS 7Y | 5,974 | -9,653,432 |
| IRS 9Y | -5,272 | 6,847,970 |
| FRA 6x12 | -5,265 | 106,098,819 |
| FRA 12x18 | -3,235 | 66,941,728 |
| DEPOSIT 6M | -2,845 | 57,071,904 |
| FRA 18x24 | -2,704 | 56,212,683 |
| FRA 1x7 | -1,619 | 32,557,361 |
| OIS 12Y | -483 | 487,737 |
| IRS 20Y | 364 | -256,335 |
| OIS 7Y | -213 | 338,510 |
| OIS 4Y | -175 | 465,238 |
| OIS 10Y | -166 | 194,464 |
| OIS 8Y | -165 | 233,155 |
| OIS 6Y | -156 | 286,136 |
| OIS 9Y | -136 | 173,879 |
| OIS 9M | -121 | 1,630,008 |
| OIS 5Y | -114 | 246,828 |

## IRRBB, ΔEVE (BCBS 2016, EUR, EBA floor)

| Scenario | Hagan-West | Log-linear |
|---|---:|---:|
| parallel_up | 5,942,941 | 5,942,396 |
| parallel_down | -9,557,624 | -9,556,810 |
| short_up | -3,529,459 | -3,514,878 |
| short_down | 3,665,135 | 3,642,874 |
| steepener | 6,757,166 | 6,735,581 |
| flattener | -6,076,958 | -6,060,827 |

Worst scenario: parallel_down (-9,557,624 EUR). Shocks exported for project 04 in `studies/irrbb_shocks.yaml` (bp per maturity, before the floor).

## Bucket locality: swap P10Y-2024 alone (payer, EUR 25m, 2.80%, maturity 2034-03-15)

A spot swap of quoted tenor (P10Y) has its dates on the pillars: its buckets are identical under both interpolations (IRS 10Y + OIS). P10Y-2024 has its dates between pillars, so the interpolation matters.

| Instrument | Hagan-West | Log-linear |
|---|---:|---:|
| OIS 1W | -1.5 | -0.8 |
| OIS 2M | -1.9 | -0.1 |
| OIS 3M | 7.6 | 4.8 |
| OIS 6M | 26.2 | 25.5 |
| OIS 9M | -13.5 | -15.8 |
| OIS 1Y | -60.4 | -51.4 |
| OIS 18M | 75.8 | 73.6 |
| OIS 2Y | -82.9 | -75.1 |
| OIS 3Y | -16.9 | -41.4 |
| OIS 4Y | -75.4 | -57.3 |
| OIS 5Y | -61.4 | -69.6 |
| OIS 6Y | -79.5 | -86.9 |
| OIS 7Y | -119.0 | -157.2 |
| OIS 8Y | -34.9 | 20.0 |
| OIS 9Y | 6.4 | -0.0 |
| OIS 10Y | -2.0 | -0.0 |
| DEPOSIT 6M | -1,681.6 | -923.8 |
| FRA 1x7 | 759.9 | -0.0 |
| FRA 2x8 | -6.3 | -0.0 |
| FRA 3x9 | 21.1 | 19.6 |
| FRA 6x12 | -11.2 | -15.2 |
| FRA 9x15 | 4.5 | 10.2 |
| FRA 12x18 | -1.5 | -5.3 |
| FRA 18x24 | -4.1 | -0.2 |
| IRS 3Y | 4.4 | 1.8 |
| IRS 4Y | 2.0 | -1.1 |
| IRS 6Y | -121.8 | 2.3 |
| IRS 7Y | 5,981.4 | 9,753.1 |
| IRS 8Y | 15,578.0 | 6,427.4 |
| IRS 9Y | -5,257.3 | -0.0 |

Share of |buckets| outside IRS 7Y and 8Y: Hagan-West 28.4%, log-linear 9.3%; instruments above 1 EUR/bp: 30 against 22.
