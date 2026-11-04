# Data assumptions

> **Levels reconstructed on 2026-11-01** from public ECB series. The validation against QuantLib does not depend on
> where the quotes come from; the interpolation studies and the PnL explain run on synthetic data. The file also
> accepts real quotes (`source = real`).

## Why reconstruct

No free source publishes EUR swap quotes (€STR OIS, IRS against EURIBOR 6M). The only free data are the ECB's. The
quotes in `data/quotes.csv` are therefore **reconstructed** from them. Their levels and dynamics are realistic, but
they are not market prices.

## Sources (free API data-api.ecb.europa.eu, versioned cache in `data/ecb/`)

| Series | ECB code | Use |
|--------|----------|-----|
| €STR | `EST.B.EU000A2X2A25.WT` | ON fixing, short-end anchor |
| Euro area AAA curve (Svensson) | `YC.B.U2.EUR.4F.G_N_A.SV_C_YM.BETA0…BETA3, TAU1, TAU2` | curve shape |
| AAA 1-year and 10-year zero rates | `…SV_C_YM.SR_1Y`, `…SR_10Y` | check of the Svensson formula |
| EURIBOR 6M, monthly average | `FM.M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA` | anchor of the 6M basis |
| Deposit facility | `FM.D.U2.EUR.4F.KR.DFR.LEV` | consistency check of the €STR |

Window: 255 quote days, from 2025-10-30 to 2026-10-29. These are the days on which both the AAA curve and the €STR
are published.

## Reconstruction, step by step

1. **€STR discount curve.**
   - Start from the Svensson AAA zero (continuous compounding).
   - Add the gap between the €STR (converted to continuous compounding) and the instantaneous AAA zero (β0 + β1).
   - That gap dies out as exp(−t / 1 year).
   - The short end thus sticks to the €STR and the long end stays the AAA curve.
2. **OIS quotes** (1W to 30Y), computed at par with the real conventions.
   - Spot start T+2.
   - A single cash flow up to 1 year, then annual cash flows.
   - ACT/360 day count.
   - MF convention with the end-of-month rule.
   - Payment delayed by one business day.
3. **EURIBOR 6M − OIS basis**: each month, it equals the ECB monthly average of EURIBOR 6M minus the average of the
   reconstructed 6M OIS forward over the same days.
   - The basis is the same for every maturity and constant within the month.
   - October 2026 is not published yet: the September basis is kept.
4. **EURIBOR 6M quotes**: OIS forward + basis.
   - 6M deposit.
   - FRAs from 1x7 to 18x24.
   - IRS from 2Y to 30Y: annual fixed 30/360, semi-annual floating ACT/360, MF, backward schedule.
5. **Noise and event.**
   - Gaussian noise, with a fixed seed (20261101) and a standard deviation per instrument:
     - OIS: 0.2 bp;
     - IRS: 0.3 bp;
     - FRA: 0.4 bp;
     - deposit: 0.5 bp.
   - Basis jump of +2.5 bp on the 10Y IRS for 5 quote days, from 2026-05-04. It is used to test anomaly detection
     and the PnL explain.
   - The €STR fixing is the published figure, without noise.

## Assumptions and their estimated impact

| Assumption | Testable? | Estimated impact |
|------------|-----------|------------------|
| €STR curve = AAA curve + short-end gap dying out in 1 year | **No**: no free OIS quotes | Mean gap over the year: +2.4 bp at 3 months, +1.1 bp at 1 year, +0.4 bp at 2 years, zero beyond 5 years. Extremes: −14.4 / +19.5 bp at 3 months. Beyond 5 years, the OIS curve is the AAA sovereign curve; in reality, the long-end swap-sovereign spread is a few tens of bp. |
| 6M basis flat in maturity, constant within the month | Partly: the monthly average of the reconstructed 6M deposit falls back on the ECB EURIBOR (tested) | Monthly basis between 14.0 and 26.8 bp. In reality, the term structure of the basis is missing and the basis jumps at month changes. |
| EURIBOR forward taken over the accrual period, not the fixing period (T−2) | Yes, in order of magnitude | Less than 0.1 bp |
| Window = days on which both the AAA curve and the €STR are published | Yes | No impact on levels |

Automatic checks (`tests/test_quotes.py`):
- the Svensson formula reproduces the ECB 1-year and 10-year zeros within 1e-6 %;
- the €STR stays between 0 and 15 bp below the deposit facility;
- the IRS − OIS basis stays positive and below 40 bp;
- regeneration reproduces the versioned file exactly;
- malformed files are rejected.

## Regenerate

```bash
python -m ratecurves.quotes   # rewrites data/quotes.csv and prints the figures above
```

To download the ECB series again: `from ratecurves.ecb import SERIES, series; [series(n, refresh=True) for n in SERIES]`.
