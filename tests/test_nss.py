"""NSS : formule contrôlée contre les taux zéro publiés par la BCE, aller-retour de l'ajustement."""
import numpy as np
import pytest

from courbes import cotations as c
from courbes.donnees import serie
from courbes.nss import ajuster, zero


@pytest.mark.parametrize("nom,t", [("sr_3m", 0.25), ("sr_1y", 1.0), ("sr_5y", 5.0), ("sr_10y", 10.0), ("sr_30y", 30.0)])
def test_formule_reproduit_les_taux_zero_bce(nom, t):
    m = c._marche()  # paramètres BCE quotidiens (β en %, τ1, τ2)
    bce = serie(nom).loc[m.index].values
    nous = np.array([zero([t], r.iloc[:4], r.iloc[4], r.iloc[5])[0] for _, r in m.iterrows()])
    assert np.max(np.abs(nous - bce)) * 100 < 0.01  # bp ; la BCE publie 6 décimales


def test_limite_court_terme():
    assert zero([0.0], [0.03, -0.01, 0.02, 0.01], 2.0, 8.0)[0] == pytest.approx(0.02, abs=1e-12)


def test_aller_retour_sans_bruit():
    t = np.array([0.02, 0.1, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    vrai = ([0.025, -0.01, 0.015, -0.02], 1.5, 9.0)
    k = ajuster(t, zero(t, *vrai))
    assert k.rmse < 1e-9
    fin = np.linspace(0, 40, 400)
    assert np.max(np.abs(k.zero(fin) - zero(fin, *vrai))) < 1e-7  # mêmes zéros, même hors des points d'ajustement


def test_rmse_reflete_le_bruit():
    t = np.linspace(0.1, 30, 25)
    bruit = np.random.default_rng(7).normal(0, 1e-4, t.size)  # 1 bp
    k = ajuster(t, zero(t, [0.03, -0.01, 0.01, 0.005], 2.0, 10.0) + bruit)
    assert 0.5e-4 < k.rmse < 1.2e-4
