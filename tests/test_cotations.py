"""Cotations reconstituées : reproductibilité, cohérence avec les séries BCE, validation du format."""
import numpy as np
import pandas as pd
import pytest

from courbes import cotations as c
from courbes import dates as dt
from courbes.donnees import serie

FIN_COURTE = pd.Timestamp("2025-11-28").date()


@pytest.fixture(scope="module")
def fichier():
    return c.lire_cotations()


@pytest.fixture(scope="module")
def sans_bruit():
    return c.reconstituer(fin=FIN_COURTE, bruit=False)


def test_regeneration_identique_au_fichier_versionne(fichier):
    pd.testing.assert_frame_equal(c.reconstituer(), fichier)


def test_graine_change_le_bruit_seulement():
    a = c.reconstituer(fin=FIN_COURTE, graine=1)
    b = c.reconstituer(fin=FIN_COURTE, graine=2)
    ecart = (a.taux - b.taux).abs() * 100
    assert 0 < ecart.max() < 3  # quelques bp au plus
    assert (ecart[a.type == "ESTR"] == 0).all()


def test_svensson_reproduit_les_taux_zero_bce():
    m = c._marche()
    for nom, t in (("sr_1y", 1.0), ("sr_10y", 10.0)):
        bce = serie(nom).loc[m.index]
        modele = [c.svensson(t, *r.iloc[:6]) for _, r in m.iterrows()]
        assert np.max(np.abs(np.array(modele) - bce.values)) < 1e-6


def test_estr_proche_du_taux_de_depot():
    m = c._marche()
    ecart = (m.estr - serie("dfr").reindex(m.index)) * 100
    assert ecart.between(-15, 0).all()  # €STR quelques bp sous la facilité de dépôt


def test_base_ancree_sur_euribor_mensuel(sans_bruit):
    depot = sans_bruit[sans_bruit.type == "DEPOT"]
    nov = depot[[f"{d:%Y-%m}" == "2025-11" for d in depot.date]].taux.mean()
    assert nov == pytest.approx(serie("euribor6m")["2025-11"], abs=1e-4)


def test_ordres_de_grandeur(sans_bruit):
    for jour, g in sans_bruit.groupby("date"):
        q = dict(zip(g.type + " " + g.tenor, g.taux))
        assert abs(q["OIS 1W"] - q["ESTR ON"]) < 0.10
        for t in c.IRS_TENORS:
            assert 0.05 < q[f"IRS {t}"] - q[f"OIS {t}"] < 0.40  # base 6M positive et raisonnable
        assert all(0 < v < 10 for v in q.values())


def test_saut_de_base_present(fichier):
    s = c.SAUT
    q = fichier[(fichier.type == s["type"]) & (fichier.tenor == s["tenor"])].set_index("date").taux
    sans = c.reconstituer(debut=s["debut"], fin=s["debut"], bruit=False)
    ref = sans[(sans.type == s["type"]) & (sans.tenor == s["tenor"])].taux.iloc[0]
    assert q[s["debut"]] - ref == pytest.approx(s["bp"] / 100, abs=0.02)


def test_ois_un_an_flux_unique():
    jour = pd.Timestamp("2026-03-02").date()
    P = lambda d: np.exp(-0.02 * dt.year_fraction(jour, d, "ACT/365F"))
    spot = dt.add_business_days(jour, 2)
    fin = dt.advance(spot, "1Y", "MF", eom=True)
    attendu = (P(spot) / P(fin) - 1) / dt.year_fraction(spot, fin, "ACT/360")
    assert c.ois_par(P, spot, "1Y") == pytest.approx(attendu, abs=1e-14)


def test_cotations_reelles_acceptees(tmp_path):
    p = tmp_path / "reel.csv"
    p.write_text("date,type,tenor,taux,source\n2026-10-29,ESTR,ON,2.439,reel\n2026-10-29,FRA,3x9,3.1,reel\n"
                 "2026-10-29,IRS,10Y,3.6,reel\n")
    assert len(c.lire_cotations(p)) == 3


@pytest.mark.parametrize("ligne", ["2026-10-29,SWAP,10Y,3.6,reel", "2026-10-29,IRS,10Q,3.6,reel",
                                   "2026-10-29,FRA,9x3,3.6,reel", "2026-10-29,IRS,10Y,3.6,bloomberg",
                                   "2026-10-29,IRS,10Y,inf,reel", "29/10/2026,IRS,10Y,3.6,reel"])
def test_cotations_invalides_rejetees(tmp_path, ligne):
    p = tmp_path / "faux.csv"
    p.write_text("date,type,tenor,taux,source\n" + ligne + "\n")
    with pytest.raises(ValueError):
        c.lire_cotations(p)
