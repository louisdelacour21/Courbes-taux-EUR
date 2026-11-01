"""Hagan-West monotone convexe : primitive g, conservation de ∫f, continuité du forward, jacobien, banc QuantLib."""
from datetime import date, timedelta

import numpy as np
import pytest

from courbes import cotations as c
from courbes.curves import CourbeHW, courbe_estr, courbe_euribor6m, primitive_g
from ql_banc import courbe_estr as estr_ql, courbe_euribor6m as e6m_ql, jours_du_banc, q

JOUR = date(2026, 3, 2)
TOL_QL = 1e-10  # même tolérance que le log-linéaire : avec ConvexMonotone(0, 1, False), écarts observés ~1e-14
COT = c.lire_cotations()

# une paire (g0, g1) par région de l'article : (i) quadratique, (ii), (iii), (iv) même signe, et les symétriques
REGIONS = [(-1.0, 1.0), (1.0, -1.5), (-1.0, 3.0), (1.0, -3.0), (2.0, -0.5), (-2.0, 0.5), (1.0, 2.0), (-1.0, -0.3)]


@pytest.mark.parametrize("g0,g1", REGIONS)
def test_primitive_g(g0, g1):
    assert primitive_g(g0, g1, 0.0) == 0.0
    assert primitive_g(g0, g1, 1.0) == pytest.approx(0.0, abs=1e-15)  # ∫g = 0 : conservation de ∫f
    h = 1e-6
    assert (primitive_g(g0, g1, h) / h) == pytest.approx(g0, abs=1e-5)  # g(0) = g0
    assert ((primitive_g(g0, g1, 1.0) - primitive_g(g0, g1, 1 - h)) / h) == pytest.approx(g1, abs=1e-5)  # g(1) = g1


def courbe_article():
    """Jeu de l'article (de mémoire : non vérifié contre les tableaux publiés) : taux zéro à 0,1 / 1 / 4 / 9 / 20 / 30 ans."""
    t = [0.1, 1, 4, 9, 20, 30]
    r = [0.081, 0.07, 0.044, 0.07, 0.04, 0.03]
    piliers = [JOUR + timedelta(days=round(x * 365)) for x in t]
    x = [-ri * (p - JOUR).days / 365 for ri, p in zip(r, piliers)]
    return CourbeHW(JOUR, piliers, x)


def forward(k, d, h=1):
    return (k.ln_p(d) - k.ln_p(d + timedelta(days=h))) * 365 / h


def test_conservation_et_continuite_article():
    k = courbe_article()
    for p, xi in zip(k.piliers, k.x):
        assert k.ln_p(p) == pytest.approx(xi, abs=1e-15)  # ∫f sur chaque intervalle = forward discret × durée
    for p in k.piliers[:-1]:  # au dernier, saut voulu vers le forward discret prolongé
        gauche = (k.ln_p(p - timedelta(days=1)) - k.ln_p(p)) * 365
        assert abs(gauche - forward(k, p)) < 2e-4, p  # forward continu au nœud (écart d'ordre f'·1 jour)
    f = [forward(k, JOUR + timedelta(days=d)) for d in range(0, 30 * 365, 7)]
    assert min(f) > 0  # pas d'oscillation sous zéro malgré des zéros très irréguliers


def test_courbe_plate_exacte():
    piliers = [JOUR + timedelta(days=d) for d in (90, 400, 2000, 7000)]
    k = CourbeHW(JOUR, piliers, [-0.03 * (p - JOUR).days / 365 for p in piliers])
    for d in range(0, 10000, 37):
        assert forward(k, JOUR + timedelta(days=d)) == pytest.approx(0.03, abs=1e-12)


def test_jacobien_hw_egal_aux_differences_finies():
    g = COT[(COT.date == JOUR) & (COT.type == "OIS")]
    k = courbe_estr(JOUR, dict(zip(g.tenor, g.taux)), CourbeHW)
    # pas minuscule : g ~ 1e-6 à court terme, un choc plus gros change de région (Hagan-West n'y est pas dérivable)
    h = 1e-9
    for j in range(len(k.x)):
        xp, xm = k.x.copy(), k.x.copy()
        xp[j] += h
        xm[j] -= h
        kp, km = CourbeHW(JOUR, k.piliers, xp), CourbeHW(JOUR, k.piliers, xm)
        fd = [(i.taux(kp.P) - i.taux(km.P)) / (2 * h) for i in k.instruments]
        assert np.allclose(k.jacobien[:, j], fd, rtol=1e-3, atol=1e-5), j


@pytest.mark.parametrize("jour", jours_du_banc(COT)[::3], ids=str)
def test_hw_identique_a_quantlib(jour):
    g = COT[COT.date == jour]
    o = g[g.type == "OIS"]
    ois = dict(zip(o.tenor, o.taux))
    six = {f"{r.type} {r.tenor}": r.taux for r in g[g.type.isin(["DEPOT", "FRA", "IRS"])].itertuples()}
    estr = courbe_estr(jour, ois, CourbeHW)
    kql, _ = estr_ql(jour, ois, hw=True)
    c6 = courbe_euribor6m(jour, six, estr, CourbeHW)
    k6, _ = e6m_ql(jour, c6.instruments, [v * 100 for v in c6.cotations], kql, hw=True)
    for d in range(0, 40 * 365, 13):
        x = jour + timedelta(days=d)
        assert abs(estr.P(x) - kql.discount(q(x))) < TOL_QL, x
        assert abs(c6.P(x) - k6.discount(q(x))) < TOL_QL, x
