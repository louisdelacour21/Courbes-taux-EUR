"""NSS: formula checked against the zero rates published by the ECB, fit round trip."""
import numpy as np
import pytest

from ratecurves import quotes as c
from ratecurves.ecb import series
from ratecurves.nss import fit, zero


@pytest.mark.parametrize("name,t", [("sr_3m", 0.25), ("sr_1y", 1.0), ("sr_5y", 5.0), ("sr_10y", 10.0), ("sr_30y", 30.0)])
def test_formula_reproduces_ecb_zero_rates(name, t):
    m = c._market()  # daily ECB parameters (β in %, τ1, τ2)
    ecb = series(name).loc[m.index].values
    ours = np.array([zero([t], r.iloc[:4], r.iloc[4], r.iloc[5])[0] for _, r in m.iterrows()])
    assert np.max(np.abs(ours - ecb)) * 100 < 0.01  # bp; the ECB publishes 6 decimals


def test_short_end_limit():
    assert zero([0.0], [0.03, -0.01, 0.02, 0.01], 2.0, 8.0)[0] == pytest.approx(0.02, abs=1e-12)


def test_round_trip_without_noise():
    t = np.array([0.02, 0.1, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    true = ([0.025, -0.01, 0.015, -0.02], 1.5, 9.0)
    k = fit(t, zero(t, *true))
    assert k.rmse < 1e-9
    fine = np.linspace(0, 40, 400)
    assert np.max(np.abs(k.zero(fine) - zero(fine, *true))) < 1e-7  # same zeros, even away from the fitted points


def test_rmse_reflects_the_noise():
    t = np.linspace(0.1, 30, 25)
    noise = np.random.default_rng(7).normal(0, 1e-4, t.size)  # 1 bp
    k = fit(t, zero(t, [0.03, -0.01, 0.01, 0.005], 2.0, 10.0) + noise)
    assert 0.5e-4 < k.rmse < 1.2e-4
