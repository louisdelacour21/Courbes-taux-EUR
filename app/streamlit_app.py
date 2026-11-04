"""Demo: €STR / EURIBOR 6M curves, portfolio risk, PnL explain, morning briefing.

    streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ratecurves import briefing as br  # noqa: E402
from ratecurves import dates as dt  # noqa: E402
from ratecurves import pricing as p  # noqa: E402
from ratecurves import quotes as c  # noqa: E402
from ratecurves import risk as r  # noqa: E402
from ratecurves.curves import Curve, CurveHW  # noqa: E402

INTERP = {"Hagan-West": CurveHW, "Log-linear": Curve}

st.set_page_config(page_title="EUR rate curves", layout="wide")
st.title("EUR rate curves (€STR / EURIBOR 6M) and swap pricer")
st.warning("Levels reconstructed from public ECB data (EUR swap quotes are licensed). "
           "The QuantLib validation does not depend on the data source; the interpolation and PnL explain studies "
           "run on synthetic data (0.2 to 0.5 bp noise, basis jump on the 10Y IRS).")


@st.cache_resource
def data():
    quotes = c.read_quotes()
    return quotes, sorted(quotes.date.unique()), p.read_portfolio(), p.deposit_fixings(quotes)


@st.cache_resource
def curves(day, name):
    quotes = data()[0]
    return r.build(day, *c.of_day(quotes, day), INTERP[name])


def forwards_6m(six, day):
    spot = dt.add_business_days(day, 2)
    starts = [dt.add_months(spot, m) for m in range(0, 29 * 12 + 1)]
    ends = [dt.add_months(d, 6) for d in starts]
    return pd.Series([(six.P(a) / six.P(b) - 1) / dt.year_fraction(a, b, "ACT/360") * 100 for a, b in zip(starts, ends)],
                     index=[dt.year_fraction(day, d, "ACT/365F") for d in starts])


quotes, days, pf, fx = data()
day = st.select_slider("Quote date", options=days, value=days[-1])
curve_tab, risk_tab, pnl_tab, briefing_tab, validation_tab = st.tabs(
    ["Curves", "Risk", "PnL explain", "Morning briefing", "Validation"])

with curve_tab:
    st.subheader("EURIBOR 6M forwards by interpolation (%)")
    st.line_chart(pd.DataFrame({n: forwards_6m(curves(day, n)[1], day) for n in INTERP}), x_label="years",
                  y_label="6M forward (%)")
    st.caption("Log-linear on ln P: piecewise constant, step-like forwards. Hagan-West: continuous forwards, "
               "chosen for production by the leave-one-out test.")
    e, k = curves(day, "Hagan-West")
    t = np.linspace(0.1, 30, 300)
    zero = lambda C: [-np.log(C.P(day + pd.Timedelta(days=round(u * 365)))) / u * 100 for u in t]  # noqa: E731
    st.subheader("Zero rates (%, continuous ACT/365F), Hagan-West")
    st.line_chart(pd.DataFrame({"€STR": zero(e), "EURIBOR 6M": zero(k)}, index=t), x_label="years")

with risk_tab:
    name = st.radio("Interpolation", list(INTERP), horizontal=True)
    e, k = curves(day, name)
    v, b = r.buckets(pf, day, e, k, fx)
    a, b2 = st.columns(2)
    a.metric("Portfolio value (EUR)", br.eur(v))
    b2.metric("Quote DV01 (EUR/bp)", br.eur(b.sum()))
    st.subheader("Buckets (EUR per bp of quote)")
    names = r.labels(e, k)
    st.bar_chart(pd.DataFrame({"bucket": b}, index=pd.CategoricalIndex(names, categories=names, ordered=True)))
    st.subheader("Swaps")
    st.dataframe(pd.DataFrame([{"swap": s.name, "start": s.start, "tenor": s.tenor, "fixed rate (%)": s.K * 100,
                                "notional": s.N, "side": "payer" if s.payer else "receiver",
                                "value (EUR)": round(s.value(day, k.P, e.P, fx))} for s in pf]), hide_index=True)
    st.subheader("IRRBB: ΔEVE per BCBS scenario (EUR)")
    st.dataframe(pd.Series(r.irrbb(pf, day, e, k, fx), name="ΔEVE").round(0), width=400)

with pnl_tab:
    s = pd.read_csv(ROOT / "studies" / "pnl_series.csv", parse_dates=["day"]).set_index("day")
    st.info("Synthetic market and reconstructed fixings: the series validates the decomposition mechanics, not "
            "market behaviour. Precomputed results (studies/pnl.py, about 10 min).")
    a, b2, c3 = st.columns(3)
    a.metric("Mean residual / mean PnL (absolute values)", f"{s.residual.abs().mean() / s.total.abs().mean():.1%}")
    b2.metric("PnL variance explained", f"{1 - s.residual.var() / s.total.var():.2%}")
    c3.metric("Log-linear twin", f"{s.residual_loglin.abs().mean() / s.total.abs().mean():.2%}")
    st.subheader("Cumulative PnL by component (EUR)")
    st.area_chart(s[["carry", "fixings", "delta", "gamma", "residual"]].cumsum())
    st.subheader("Daily residual (EUR): Hagan-West against log-linear")
    st.line_chart(s[["residual", "residual_loglin"]])
    st.markdown((ROOT / "studies" / "pnl.md").read_text(encoding="utf-8").split("\n", 4)[4])

with briefing_tab:
    if day == days[0]:
        st.write("No previous day for the first day.")
    else:
        st.code(br.text(br.briefing(day)), language=None)

with validation_tab:
    for f in ["leave_one_out.md", "nss.md", "risk.md"]:
        with st.expander(f):
            st.markdown((ROOT / "studies" / f).read_text(encoding="utf-8"))
