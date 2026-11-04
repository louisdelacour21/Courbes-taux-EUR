"""Reconstructed quotes: reproducibility, consistency with the ECB series, format validation."""
import numpy as np
import pandas as pd
import pytest

from ratecurves import dates as dt
from ratecurves import quotes as c
from ratecurves.ecb import series

SHORT_END = pd.Timestamp("2025-11-28").date()


@pytest.fixture(scope="module")
def file():
    return c.read_quotes()


@pytest.fixture(scope="module")
def noiseless():
    return c.reconstruct(end=SHORT_END, noise=False)


def test_regeneration_identical_to_versioned_file(file):
    pd.testing.assert_frame_equal(c.reconstruct(), file)


def test_seed_changes_the_noise_only():
    a = c.reconstruct(end=SHORT_END, seed=1)
    b = c.reconstruct(end=SHORT_END, seed=2)
    gap = (a.rate - b.rate).abs() * 100
    assert 0 < gap.max() < 3  # a few bp at most
    assert (gap[a.type == "ESTR"] == 0).all()


def test_svensson_reproduces_ecb_zero_rates():
    m = c._market()
    for name, t in (("sr_1y", 1.0), ("sr_10y", 10.0)):
        ecb = series(name).loc[m.index]
        model = [c.svensson(t, *r.iloc[:6]) for _, r in m.iterrows()]
        assert np.max(np.abs(np.array(model) - ecb.values)) < 1e-6


def test_estr_close_to_deposit_facility_rate():
    m = c._market()
    gap = (m.estr - series("dfr").reindex(m.index)) * 100
    assert gap.between(-15, 0).all()  # €STR a few bp below the deposit facility


def test_basis_anchored_on_monthly_euribor(noiseless):
    dep = noiseless[noiseless.type == "DEPOSIT"]
    nov = dep[[f"{d:%Y-%m}" == "2025-11" for d in dep.date]].rate.mean()
    assert nov == pytest.approx(series("euribor6m")["2025-11"], abs=1e-4)


def test_orders_of_magnitude(noiseless):
    for day, g in noiseless.groupby("date"):
        q = dict(zip(g.type + " " + g.tenor, g.rate))
        assert abs(q["OIS 1W"] - q["ESTR ON"]) < 0.10
        for t in c.IRS_TENORS:
            assert 0.05 < q[f"IRS {t}"] - q[f"OIS {t}"] < 0.40  # positive and reasonable 6M basis
        assert all(0 < v < 10 for v in q.values())


def test_basis_jump_present(file):
    s = c.JUMP
    q = file[(file.type == s["type"]) & (file.tenor == s["tenor"])].set_index("date").rate
    clean = c.reconstruct(start=s["start"], end=s["start"], noise=False)
    ref = clean[(clean.type == s["type"]) & (clean.tenor == s["tenor"])].rate.iloc[0]
    assert q[s["start"]] - ref == pytest.approx(s["bp"] / 100, abs=0.02)


def test_one_year_ois_single_cashflow():
    day = pd.Timestamp("2026-03-02").date()
    P = lambda d: np.exp(-0.02 * dt.year_fraction(day, d, "ACT/365F"))
    spot = dt.add_business_days(day, 2)
    end = dt.advance(spot, "1Y", "MF", eom=True)
    expected = (P(spot) / P(end) - 1) / dt.year_fraction(spot, end, "ACT/360")
    assert c.ois_par(P, spot, "1Y") == pytest.approx(expected, abs=1e-14)


def test_real_quotes_accepted(tmp_path):
    p = tmp_path / "real.csv"
    p.write_text("date,type,tenor,rate,source\n2026-10-29,ESTR,ON,2.439,real\n2026-10-29,FRA,3x9,3.1,real\n"
                 "2026-10-29,IRS,10Y,3.6,real\n")
    assert len(c.read_quotes(p)) == 3


@pytest.mark.parametrize("row", ["2026-10-29,SWAP,10Y,3.6,real", "2026-10-29,IRS,10Q,3.6,real",
                                 "2026-10-29,FRA,9x3,3.6,real", "2026-10-29,IRS,10Y,3.6,bloomberg",
                                 "2026-10-29,IRS,10Y,inf,real", "29/10/2026,IRS,10Y,3.6,real"])
def test_invalid_quotes_rejected(tmp_path, row):
    p = tmp_path / "bad.csv"
    p.write_text("date,type,tenor,rate,source\n" + row + "\n")
    with pytest.raises(ValueError):
        c.read_quotes(p)
