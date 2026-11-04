# NSS fitted to the bootstrapped zeros (Hagan-West)

255 days of noisy quotes; noiseless control one day in ten (26 days). Fit to the pillar zeros, equal weights.

| Curve | Quotes | Mean RMSE (bp) | Max RMSE (bp) | Max residual (bp) |
|---|---|---|---|---|
| €STR | noisy | 0.55 | 1.86 | 6.17 |
| 6M | noisy | 0.67 | 1.87 | 6.02 |
| €STR | noiseless | 0.44 | 1.61 | 5.46 |
| 6M | noiseless | 0.50 | 1.70 | 5.34 |

Day-to-day stability (noisy quotes): standard deviation of daily changes, in bp, and number of days where a λ moves by more than 50%.

| Curve | Δ 10Y zero | Δ β0 (level) | Δ β1 (−slope) | Δ β2 (curvature) | Δ β3 | λ jumps |
|---|---|---|---|---|---|---|
| €STR | 3.4 | 52.8 | 52.9 | 50.6 | 211.6 | 19 |
| 6M | 3.5 | 75.8 | 76.6 | 82.0 | 288.9 | 32 |

Extrapolation at 40 years, NSS minus extended flat forward (bp): €STR mean -5.5, min -16.6, max +15.9; 6M mean -5.7, min -17.3, max +15.9
