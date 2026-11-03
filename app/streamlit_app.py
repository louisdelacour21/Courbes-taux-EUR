"""Démo : courbes €STR / EURIBOR 6M, risques du portefeuille, PnL explain, synthèse du matin.

    streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from courbes import cotations as c  # noqa: E402
from courbes import dates as dt  # noqa: E402
from courbes import pricing as p  # noqa: E402
from courbes import risque as r  # noqa: E402
from courbes import synthese as sy  # noqa: E402
from courbes.curves import Courbe, CourbeHW  # noqa: E402

INTERP = {"Hagan-West": CourbeHW, "Log-linéaire": Courbe}

st.set_page_config(page_title="Courbes de taux EUR", layout="wide")
st.title("Courbes de taux EUR (€STR / EURIBOR 6M) et pricer de swaps")
st.warning("Niveaux reconstitués depuis les données publiques BCE (les cotations de swaps EUR sont sous licence). "
           "La validation contre QuantLib est indépendante de la provenance ; les études d'interpolation et de "
           "PnL explain portent sur des données synthétiques (bruit 0,2 à 0,5 bp, saut de base sur l'IRS 10Y).")


@st.cache_resource
def donnees():
    cot = c.lire_cotations()
    return cot, sorted(cot.date.unique()), p.lire_portefeuille(), p.fixings_depot(cot)


@st.cache_resource
def courbes(jour, nom):
    cot = donnees()[0]
    return r.construire(jour, *c.du_jour(cot, jour), INTERP[nom])


def forwards_6m(six, jour):
    spot = dt.add_business_days(jour, 2)
    debuts = [dt.add_months(spot, m) for m in range(0, 29 * 12 + 1)]
    fins = [dt.add_months(d, 6) for d in debuts]
    return pd.Series([(six.P(a) / six.P(b) - 1) / dt.year_fraction(a, b, "ACT/360") * 100 for a, b in zip(debuts, fins)],
                     index=[dt.year_fraction(jour, d, "ACT/365F") for d in debuts])


cot, jours, pf, fx = donnees()
jour = st.select_slider("Date de cotation", options=jours, value=jours[-1])
courbe_tab, risque_tab, pnl_tab, synthese_tab, validation_tab = st.tabs(
    ["Courbes", "Risques", "PnL explain", "Synthèse du matin", "Validation"])

with courbe_tab:
    st.subheader("Forwards EURIBOR 6M selon l'interpolation (%)")
    st.line_chart(pd.DataFrame({n: forwards_6m(courbes(jour, n)[1], jour) for n in INTERP}), x_label="années",
                  y_label="forward 6M (%)")
    st.caption("Log-linéaire sur ln P : forwards constants par morceaux, en escalier. Hagan-West : forwards continus, "
               "choisi en production par le test leave-one-out.")
    e, k = courbes(jour, "Hagan-West")
    t = np.linspace(0.1, 30, 300)
    zero = lambda C: [-np.log(C.P(jour + pd.Timedelta(days=round(u * 365)))) / u * 100 for u in t]  # noqa: E731
    st.subheader("Taux zéro (%, continus ACT/365F), Hagan-West")
    st.line_chart(pd.DataFrame({"€STR": zero(e), "EURIBOR 6M": zero(k)}, index=t), x_label="années")

with risque_tab:
    nom = st.radio("Interpolation", list(INTERP), horizontal=True)
    e, k = courbes(jour, nom)
    v, b = r.buckets(pf, jour, e, k, fx)
    a, b2 = st.columns(2)
    a.metric("Valeur du portefeuille (EUR)", sy.eur(v))
    b2.metric("DV01 par cotations (EUR/bp)", sy.eur(b.sum()))
    st.subheader("Buckets (EUR par bp de cotation)")
    noms = r.libelles(e, k)
    st.bar_chart(pd.DataFrame({"bucket": b}, index=pd.CategoricalIndex(noms, categories=noms, ordered=True)))
    st.subheader("Swaps")
    st.dataframe(pd.DataFrame([{"swap": s.nom, "départ": s.debut, "ténor": s.tenor, "taux fixe (%)": s.K * 100,
                                "notionnel": s.N, "sens": "payeur" if s.payeur else "receveur",
                                "valeur (EUR)": round(s.valeur(jour, k.P, e.P, fx))} for s in pf]), hide_index=True)
    st.subheader("IRRBB : ΔEVE par scénario BCBS (EUR)")
    st.dataframe(pd.Series(r.irrbb(pf, jour, e, k, fx), name="ΔEVE").round(0), width=400)

with pnl_tab:
    s = pd.read_csv(RACINE / "etudes" / "pnl_serie.csv", parse_dates=["jour"]).set_index("jour")
    st.info("Marché synthétique et fixings reconstitués : la série valide la mécanique de décomposition, pas un "
            "comportement de marché. Résultats précalculés (etudes/pnl.py, environ 10 min).")
    a, b2, c3 = st.columns(3)
    a.metric("Résiduel moyen / PnL moyen (valeurs absolues)", f"{s.residuel.abs().mean() / s.total.abs().mean():.1%}")
    b2.metric("Variance du PnL expliquée", f"{1 - s.residuel.var() / s.total.var():.2%}")
    c3.metric("Témoin log-linéaire", f"{s.residuel_loglin.abs().mean() / s.total.abs().mean():.2%}")
    st.subheader("PnL cumulé par composante (EUR)")
    st.area_chart(s[["portage", "fixings", "delta", "gamma", "residuel"]].cumsum())
    st.subheader("Résiduel quotidien (EUR) : Hagan-West contre log-linéaire")
    st.line_chart(s[["residuel", "residuel_loglin"]])
    st.markdown((RACINE / "etudes" / "pnl.md").read_text(encoding="utf-8").split("\n", 4)[4])

with synthese_tab:
    if jour == jours[0]:
        st.write("Pas de veille pour le premier jour.")
    else:
        st.code(sy.texte(sy.synthese(jour)), language=None)

with validation_tab:
    for f in ["leave_one_out.md", "nss.md", "risque.md"]:
        with st.expander(f):
            st.markdown((RACINE / "etudes" / f).read_text(encoding="utf-8"))
