# Multi-curve EUR rate curves and swap pricer

Bootstrap an €STR discount curve and a EURIBOR 6M projection curve, price a swap portfolio (DV01, pillar risks,
PnL explain), all reproduced exactly by QuantLib.

## Progress

| # | Step | Status |
|---|------|--------|
| 1 | Date engine checked day by day against QuantLib (2000-2060) | done |
| 2 | ECB data, reconstruction, `assumptions.md` | done |
| 3 | Log-linear €STR curve, global Newton | done |
| 4 | QuantLib €STR bench (gaps < 1e-10 in CI) | done |
| 5 | EURIBOR 6M curve + QuantLib bench | done |
| 6 | Hagan-West + leave-one-out | done |
| 7 | NSS | done |
| 8 | Pricer, buckets, hedging, IRRBB | done |
| 9 | PnL explain | done |
| 10 | Demo, morning briefing, validation report | done (online deployment pending) |

## Date engine (`ratecurves/dates.py`)

- **TARGET2** calendar (weekends, 1 January, Good Friday, Easter Monday, 1 May, 25 and 26 December).
- Business day conventions: following, modified following, preceding, modified preceding, unadjusted.
- Tenors (`"2D"`, `"1W"`, `"6M"`, `"10Y"`) with the end-of-month rule.
- Day counts: ACT/360, ACT/365F, 30/360 Bond Basis.
- Schedules generated backwards from maturity (short front stub), with or without end of month.

**Validation** (`tests/test_dates.py`, 48 tests): comparison with QuantLib on every day from 2000 to 2060
(business days, adjustments, month ends), on thousands of random tenors, date pairs and schedules (fixed seed).
No gap tolerated.

Behaviour difference noted: with the end-of-month rule, QuantLib 1.44 adjusts the intermediate dates from the last
*calendar* day of the month; under following, a 31 October falling on a Sunday therefore becomes 1 November. The
engine reproduces this behaviour.

## Data (`ratecurves/ecb.py`, `ratecurves/quotes.py`)

> Levels reconstructed on 2026-11-01; QuantLib validation independent of the data source; interpolation and PnL
> explain studies on synthetic data.

`data/quotes.csv` holds one year of daily quotes (€STR, OIS 1W-30Y, 6M deposit, FRAs, IRS 2Y-30Y against 6M). They
are reconstructed from free ECB series (AAA curve, €STR, monthly EURIBOR 6M), because no free source publishes swap
quotes. Method, assumptions and estimated impact: [`assumptions.md`](assumptions.md). The same format accepts real
quotes (`source = real`).

## €STR curve (`ratecurves/curves.py`, `ratecurves/instruments.py`)

- Unknowns: x_k = ln P(T_k), one pillar per OIS (last relevant date = last payment, T+1 business day).
- Log-linear interpolation in t = ACT/365F, flat forward beyond the last pillar.
- **Global Newton** with an analytic Jacobian: the curve returns dual numbers (value + gradient) that the instrument
  formulas propagate exactly. Stops at max|implied rate − quote| < 1e-13.
- The Jacobian dR/dx is kept for the pillar risks (step 8).

**Validation** (`tests/test_curves.py`):
- par repricing within 1e-13 on one day in ten of the quote year;
- Jacobian equal to finite differences within 1e-6;
- on noiseless quotes, the curve falls back on the generating curve at the pillars (~1e-6 up to 10 years).
  Between two distant pillars (25-30 years), log-linear moves away from it by up to ~2e-3 in DF: this is what step 6
  has to measure.

**QuantLib bench** (`tests/test_quantlib_estr.py`, tolerance 1e-10): the same curve is built with `OISRateHelper`
(spot 2, payment T+1 MF TARGET, end of month, `LastRelevantDate` pillar) and `PiecewiseLogLinearDiscount` in ACT/365F
(bootstrap accuracy 1e-14). The tested days are one in ten, every day whose spot falls on a month end, and the last
one. For each, the bench compares:
- the pillars;
- the discount factors on 500 dates up to 40 years;
- the par rates of the calibration instruments;
- 200 random OIS (`MakeOIS.fairRate`, forward start up to 5 years, tenor from 1W to 30Y).

Two conventions matter to get gaps of order 1e-15:
- the schedule is generated from the **unadjusted** maturity (spot + tenor);
- when the spot is the last business day of the month, the maturity moves to the last day of the month
  (end-of-month rule).

## EURIBOR 6M curve (`euribor6m_curve`)

- Instruments: 6M deposit, FRAs 1x7 to 18x24 (ACT/360, MF end of month), IRS 3Y-30Y (annual fixed 30/360 Bond Basis,
  semi-annual floating ACT/360, end of month, unadjusted maturity like the OIS).
- The 2Y IRS is dropped: its pillar coincides with that of the 18x24 FRA (QuantLib also refuses two equal pillars).
- Exogenous discounting on the €STR curve (EUR cash CSA); same global Newton, with the €STR curve held fixed.
- "Par" floating coupon (QuantLib default setting): 6M forward over the accrual period.

**QuantLib bench** (`tests/test_quantlib_euribor6m.py`, tolerance 1e-10, same days as the €STR bench):
`DepositRateHelper`, `FraRateHelper`, `SwapRateHelper` discounted on the QuantLib €STR curve. The bench compares the
pillars, the 6M discount factors on 500 dates, the par rates and 200 random swaps (`MakeVanillaSwap.fairRate`, forward
start up to 5 years, tenor from 1 to 30 years). Observed gaps of order 1e-15.

## Hagan-West and the interpolation choice (`CurveHW`, `studies/leave_one_out.py`)

**Monotone convex Hagan-West** (Hagan & West, 2006), on the same unknowns x_k = ln P(T_k):
- continuous instantaneous forward; ∫f preserved on each interval (the DFs at the pillars are exactly exp(x_k));
- four regions depending on the gap between the node forward and the discrete forward, no oscillation;
- **positivity constraint switched off**: useless with positive rates, harmful with negative rates;
- beyond the last pillar, the last discrete forward is extended, as in log-linear and in QuantLib;
- global Newton started from the log-linear solution (identical to the sequential bootstrap), stops at 1e-13.
  €STR curve build: ~0.15 s.

The Jacobian stays analytic (dual numbers), but Hagan-West is not differentiable at the region boundaries. At the
short end, the gaps g are ~1e-6: a 1e-6 bump changes region, and finite differences move away from the Jacobian. The
test therefore uses a 1e-9 bump.

**QuantLib bench** (`tests/test_hagan_west.py`): `PiecewiseConvexMonotoneForward` with
`ConvexMonotone(quadraticity=0, monotonicity=1, forcePositive=False)` reproduces our €STR and 6M curves to ~1e-14.
The tolerance did not need to be loosened: it stays at 1e-10. With the QuantLib default settings (0.3 / 0.7 / forced
positivity), the gap rises to ~1e-4 in DF: the "pure" method of the paper is not the QuantLib default.

Other tests:
- G(1) = 0, g(0) = g0 and g(1) = g1 in the four regions;
- exact flat curve;
- preservation of ∫f, continuity at the nodes and positive forward on the paper's data set. That data set (zeros at
  0.1 / 1 / 4 / 9 / 20 / 30 years) is taken from memory and has not been checked against the published tables.

**Leave-one-out** ([`studies/leave_one_out.md`](studies/leave_one_out.md)): 30 days (one in ten + the 5 days of the
10Y IRS basis jump), noisy quotes. For each day, each inner instrument is removed, the curve is rebuilt, then the
pricing error of the removed instrument is measured. Gaps in bp:

| Curve | Interpolation | Mean | Max | Roughness (bp²/year) |
|---|---|---|---|---|
| €STR | log-linear | 1.36 | 5.46 | 4.7 |
| €STR | Hagan-West | **0.32** | **1.37** | **0.7** |
| 6M | log-linear | 2.02 | 12.69 | 8.9 |
| 6M | Hagan-West | **0.62** | **3.70** | **1.1** |

**Production choice: Hagan-West.** The mean error is divided by 3 to 4 and the maximum by 3 to 4. The clearest gain
is on the FRAs (6x12 to 18x24: 5 bp against 1 bp on average). Roughness is divided by 6 to 8.

Two caveats:
- The quotes derive from a smooth Svensson curve, which favours a smooth interpolation. The ranking remains to be
  confirmed on real quotes.
- Hagan-West is not local. On the jump days, the removed 10Y IRS is repriced less well (max 3.1 bp against 2.4 bp):
  the jump spreads to the neighbours. The non-locality of the buckets is measured in step 8 (next section); log-linear
  remains available (`cls=Curve`).

## NSS (`ratecurves/nss.py`, `studies/nss.py`)

Nelson-Siegel-Svensson, ECB formula, continuously compounded zero rates:
y(τ) = β0 + β1 L(τ/λ1) + β2 [L(τ/λ1) − e^{−τ/λ1}] + β3 [L(τ/λ2) − e^{−τ/λ2}], with L(u) = (1 − e^{−u})/u.
**Use: smoothing, reading level / slope / curvature and extrapolation, never pricing** (pricing stays on the
bootstrapped curves, which reprice the instruments to 1e-13).

- β by ordinary least squares at fixed (λ1, λ2); (λ1, λ2) by a starting grid then `scipy.optimize.least_squares`.
- Identification constraints: 2 λ1 ≤ λ2 ≤ 30 years (ECB orders of magnitude: τ1 ≈ 3 years, τ2 ≈ 13 years). Without
  them, the optimum slides towards λ1 ≈ λ2: the two humps become collinear and β2 ≈ −β3 reaches ±1e3, for the same RMSE.

**Formula check** (`tests/test_nss.py`): the published ECB zero rates (series SR_3M, 1Y, 5Y, 10Y, 30Y, one year) are
reproduced from the ECB parameters within 0.01 bp. This check validates the formula, not the fit. On top of it: a
noiseless round trip (parameters recovered, zeros within 1e-7 up to 40 years) and 1 bp of noise correctly measured by
the RMSE.

**Fit to the bootstrapped zeros** ([`studies/nss.md`](studies/nss.md)): each day, NSS is fitted to the Hagan-West
zeros of the €STR and 6M pillars.

| Curve | Quotes | Mean RMSE (bp) | Max RMSE (bp) | Max residual (bp) |
|---|---|---|---|---|
| €STR | noisy | 0.55 | 1.86 | 6.17 |
| 6M | noisy | 0.67 | 1.87 | 6.02 |
| €STR | noiseless (1 day in 10) | 0.44 | 1.61 | 5.46 |
| 6M | noiseless (1 day in 10) | 0.50 | 1.70 | 5.34 |

- Even without noise, the RMSE stays at ~0.5 bp: the bootstrapped zeros are not exactly a Svensson curve. Noise only
  adds ~0.1 to 0.2 bp. The RMSE therefore mostly measures NSS's shape error; the max residuals (5-6 bp) show why NSS
  must not be used for pricing.
- **Stability**: the bootstrapped 10-year zero moves by 3.4 bp a day (standard deviation), but the β move by 50 to
  290 bp and a λ jumps by more than 50% about one day in ten (19 days for €STR, 32 for 6M). The constraints divided
  these jumps by 3 (59 and 79 without constraints) and brought the β changes from ~1e8 bp down to ~1e2 bp, for +0.1 bp
  of RMSE. The parameters remain too unstable to be read on their own day to day.
- **Extrapolation at 40 years**: NSS is on average 5.5 bp below the extended last forward of the bootstrapped curves
  (from −17 to +16 bp depending on the day).

## Pricer and risks (`ratecurves/pricing.py`, `ratecurves/risk.py`, `studies/risk.py`)

Payer swap: V = N [Σ τ_j F_j Pd(t_j) − K Σ τ_i Pd(t_i)], F_j projected on the 6M curve, €STR discounting. The
portfolio (`data/portfolio.csv`) holds ten swaps: payers and receivers, forward starts, seasoned swaps.
**Past EURIBOR 6M fixings are built by assumption**: reconstructed DEPOSIT 6M quote of the fixing day.

- **Buckets**: ∂V/∂q = (∂V/∂x) J⁻¹, with J = ∂R/∂x the global Jacobian of both curves (x = [x_€STR, x_6M],
  block triangular), obtained with dual numbers. Result in EUR per bp of quote, in 0.1 s.
- **DV01** published twice: by quotes (±1 bp, full rebootstrap) and by zero rates (+1 bp on the zeros of both
  curves). They differ by about 4% (36,256 against 37,593 EUR/bp).
- **Hedging**: h = −B⁻¹δ in calibration instruments at par; B is diagonal (annuity × 1 bp), computed without assuming
  it. Residual ~1e-12 EUR/bp.
- **IRRBB** (BCBS 2016, EUR): six shocks on the zero rates of both curves, post-shock EBA floor
  max(r + Δ, min(r, −150 + 3t bp)), full revaluation. Worst scenario: parallel down, ΔEVE −EUR 9.6m. The shocks per
  maturity are exported for project 04 (stress tests): [`studies/irrbb_shocks.yaml`](studies/irrbb_shocks.yaml).

**Checks** (`tests/test_risk.py`, in log-linear and Hagan-West):
- swap at par within 1e-10 × N;
- NPVs of the ten swaps identical to QuantLib (`MakeVanillaSwap`, `DiscountingSwapEngine`) within 1e-10 × N;
- buckets equal to quote bumps (1e-7 relative in log-linear). In Hagan-West, the gap goes up to ~1e-5 relative: the
  interpolation is not differentiable at the boundaries of its regions;
- Σ buckets = parallel DV01 within 1e-3;
- hedged portfolio with zero buckets;
- shock and floor formulas.

**Locality** ([`studies/risk.md`](studies/risk.md)): a spot swap of quoted tenor has its dates on the pillars, hence
the same buckets under both interpolations. P10Y-2024 (maturity 2034-03-15, between the 7Y and 8Y pillars) puts 28% of
its |buckets| outside IRS 7Y/8Y in Hagan-West against 9% in log-linear, including −5,257 EUR/bp on the 9Y IRS (0 in
log-linear). This is the price of the better interpolation found in step 6: a Hagan-West hedge uses more instruments.

## PnL explain (`ratecurves/pnl.py`, `studies/pnl.py`)

**Synthetic market**: reconstructed noisy quotes, reconstructed EURIBOR 6M fixings. The result validates the
decomposition mechanics, not market behaviour.

PnL(t → t+1) = carry + fixings + Σ_k bucket_k Δq_k + ½ Γ Δq̄² + residual:
- **carry**: curves of t carried to t+1 (P(d) / P(t+1)), turned into quotes q_c and rebootstrapped; fixings falling
  in [t, t+1[ taken at the forwards; paid cash flows included;
- **fixings**: gap between the published fixings and those forwards. **Component built by assumption**
  (reconstructed fixings);
- **delta**: buckets of the carried curves × (q_1 − q_c); **gamma**: parallel gamma (±1 bp, rebootstrap) × Δq̄².

Over 254 days in Hagan-West ([`studies/pnl.md`](studies/pnl.md), series in
[`studies/pnl_series.csv`](studies/pnl_series.csv)): mean residual 4.9% of the mean absolute PnL, day-by-day median
3.2%, 99.6% of the PnL variance explained. The residual comes from the non-differentiability of Hagan-West (region
changes of the monotone convex scheme): the log-linear twin drops to 0.26%. Worst day: the 10Y IRS basis jump
(2026-05-04). By analogy only, this is the spirit of the FRTB PnL attribution test (hypothetical PnL against risk
theoretical PnL).

**Checks** (`tests/test_pnl.py`, both interpolations): zero residual under pure carry; third-order residual on a
known parallel shock (ratio 8 between 10 and 5 bp shocks); paid cash flows.

The study revealed a defect, now fixed: on 33 days, the end of the 18x24 FRA and that of the 2Y IRS differ by one day,
and the 6M curve kept both (near-singular Jacobian, offsetting buckets of ±EUR 1m/bp). An IRS within 5 days of a FRA
pillar is now dropped.

## Demo, morning briefing, report (`app/`, `ratecurves/briefing.py`, `studies/report.py`)

> Levels reconstructed from public ECB data; QuantLib validation independent of the data source; interpolation and
> PnL explain studies on synthetic data.

**Streamlit demo**: `streamlit run app/streamlit_app.py`. Tabs for curves (6M forwards, log-linear against
Hagan-West), risk (buckets, swaps, IRRBB), PnL explain (precomputed series), morning briefing and validation studies.
The curves of the chosen day are built on the fly (a few tenths of a second); the PnL explain, 10 minutes of
computation, is read from `studies/pnl_series.csv`.

**Morning briefing**: `python -m ratecurves.briefing [YYYY-MM-DD]` (last day by default). Value, DV01, three largest
pillars, previous day's PnL explain and alerts: |residual| > max(10% of PnL, EUR 10,000), or a quote moving by more
than 2 bp relative to the mean of its two neighbours (isolated move, like the 10Y IRS basis jump). **Measured run
time: about 3 s** (2.6 to 3.1 s depending on the run: two days of curves, buckets and PnL decomposition). On
2026-05-04, the briefing raises the residual alert and the IRS 9Y / IRS 10Y alerts.

**Validation report**: `python studies/report.py` writes `report/validation_report.pdf` (HTML converted by headless
Edge). It is a **self-review**, not an independent validation in the SR 11-7 sense. The script recomputes every
numerical threshold: repricing (< 1e-13) and gaps to the QuantLib discount factors (< 1e-10) on the bench days, for
both interpolations, then the share of the PnL explain residual; it includes the studies as is.

Latest figures (38 bench days, 28 s):

| Interpolation | Max repricing | Max €STR DF against QuantLib | Max 6M DF against QuantLib |
|---|---:|---:|---:|
| Log-linear | 3.4e-14 | 4.5e-15 | 6.5e-14 |
| Hagan-West | 9.5e-14 | 3.0e-13 | 1.4e-13 |

PnL explain: 4.93% (log-linear twin 0.26%); 30 days out of 254 exceed the residual alert threshold.

## Running the tests

```bash
python -m pip install -e ".[test]"
python -m pytest
```

MIT licence (`LICENSE`). Free and open-source tools only (Python, NumPy, pandas, QuantLib, pytest) and public ECB data.
