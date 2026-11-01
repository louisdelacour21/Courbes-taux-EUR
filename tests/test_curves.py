"""Courbe €STR : interpolation log-linéaire, repricing au pair à 1e-13, jacobien analytique."""
from datetime import date

import numpy as np
import pytest

from courbes import cotations as c
from courbes import dates as dt
from courbes.curves import Courbe, Dual, courbe_estr

JOUR = date(2026, 3, 2)


@pytest.fixture(scope="module")
def cot():
    return c.lire_cotations()


def ois_du_jour(cot, jour):
    g = cot[(cot.date == jour) & (cot.type == "OIS")]
    return dict(zip(g.tenor, g.taux))


def test_interpolation_log_lineaire():
    piliers = [date(2027, 3, 2), date(2028, 3, 2)]
    k = Courbe(JOUR, piliers, [-0.02, -0.05])
    assert k.P(JOUR) == 1.0
    assert k.ln_p(piliers[1]) == pytest.approx(-0.05, abs=1e-15)
    t = lambda d: dt.year_fraction(JOUR, d, "ACT/365F")
    m = date(2027, 9, 1)
    w = (t(m) - t(piliers[0])) / (t(piliers[1]) - t(piliers[0]))
    assert k.ln_p(m) == pytest.approx(-0.02 + w * (-0.03), abs=1e-15)
    # au-delà du dernier pilier : forward constant (prolongement du dernier segment)
    loin = date(2030, 3, 1)
    pente = -0.03 / (t(piliers[1]) - t(piliers[0]))
    assert k.ln_p(loin) == pytest.approx(-0.05 + pente * (t(loin) - t(piliers[1])), abs=1e-15)
    with pytest.raises(ValueError):
        k.P(date(2026, 1, 1))


def test_dual_arithmetique():
    a, b = Dual(3.0, np.array([1.0, 0.0])), Dual(2.0, np.array([0.0, 1.0]))
    r = (a / b - 1) * a + 2.0 * b - 1 / a
    va, vb = 3.0, 2.0  # r = a²/b - a + 2b - 1/a
    assert r.v == pytest.approx(va**2 / vb - va + 2 * vb - 1 / va)
    np.testing.assert_allclose(r.g, [2 * va / vb - 1 + 1 / va**2, -va**2 / vb**2 + 2])


def test_repricing_au_pair_tous_les_10_jours(cot):
    jours = sorted(cot.date.unique())
    for jour in jours[::10] + [jours[-1]]:
        q = ois_du_jour(cot, jour)
        k = courbe_estr(jour, q)
        ecarts = [abs(i.taux(k.P) - q[i.tenor] / 100) for i in k.instruments]
        assert max(ecarts) < 1e-13, jour


def test_jacobien_egal_aux_differences_finies(cot):
    k = courbe_estr(JOUR, ois_du_jour(cot, JOUR))
    h = 1e-7
    for j in range(len(k.x)):
        dx = np.zeros(len(k.x))
        dx[j] = h
        haut, bas = Courbe(JOUR, k.piliers, k.x + dx), Courbe(JOUR, k.piliers, k.x - dx)
        fd = [(i.taux(haut.P) - i.taux(bas.P)) / (2 * h) for i in k.instruments]
        np.testing.assert_allclose(k.jacobien[:, j], fd, rtol=1e-6, atol=1e-9)


def test_courbe_proche_de_la_courbe_generatrice():
    """Sur cotations non bruitées, les DF bootstrappés aux piliers retombent sur la courbe qui les a générées."""
    m = c._marche()
    r = m.loc[JOUR]
    vrai = c.actualisation(JOUR, r.iloc[:6].tolist(), r.estr)
    spot = dt.add_business_days(JOUR, 2)
    q = {t: c.ois_par(vrai, spot, t) * 100 for t in c.OIS_TENORS}
    k = courbe_estr(JOUR, q)
    # les dates de flux intermédiaires (spot, coupons annuels) sont interpolées, d'où un écart aux piliers :
    # ~1e-6 jusqu'à 10 ans, jusqu'à ~4e-4 à 30 ans où les piliers sont espacés de 5 ans
    ecarts = [abs(k.P(d) / vrai(d) - 1) for d in k.piliers]
    assert max(ecarts[:18]) < 1e-5 and max(ecarts) < 5e-4
    # entre les piliers, le forward en escalier du log-linéaire s'écarte de la courbe lisse (jusqu'à ~2e-3 sur
    # le segment 25-30 ans) : c'est ce que l'étape 6 (Hagan-West, leave-one-out) doit mesurer et réduire
    entre = [JOUR + (k.piliers[-1] - JOUR) * f for f in np.linspace(0.01, 1, 200)]
    assert max(abs(k.P(d) / vrai(d) - 1) for d in entre) < 3e-3
