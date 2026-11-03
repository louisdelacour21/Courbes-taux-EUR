"""PnL explain : identité de la décomposition, résiduel nul en portage pur, d'ordre 3 sur un choc parallèle."""
from datetime import date, timedelta

import pytest

from courbes import cotations as c
from courbes import dates as dt
from courbes import pricing as p
from courbes import pnl
from courbes import risque as r
from courbes.curves import Courbe, CourbeHW

COT = c.lire_cotations()
JOURS = sorted(COT.date.unique())
J0, J1 = JOURS[-2], JOURS[-1]
PF, FIX = p.lire_portefeuille(), p.fixings_depot(COT)


def cotations(jour):
    g = COT[COT.date == jour]
    o, s6 = g[g.type == "OIS"], g[g.type.isin(["DEPOT", "FRA", "IRS"])]
    return dict(zip(o.tenor, o.taux)), dict(zip(s6.type + " " + s6.tenor, s6.taux))


def portees(classe):
    cot0 = cotations(J0)
    return cot0, pnl.cotations_portees(*r.construire(J0, *cot0, classe), *cot0, J1)


@pytest.mark.parametrize("classe", [Courbe, CourbeHW])
def test_portage_pur_residuel_nul(classe):
    cot0, qc = portees(classe)
    e = pnl.expliquer(PF, J0, J1, cot0, qc, FIX, classe)
    assert abs(e["delta"]) < 1e-6 and abs(e["gamma"]) < 1e-6 and abs(e["residuel"]) < 1e-6
    assert e["total"] == pytest.approx(e["portage"] + e["fixings"], abs=1e-6)


@pytest.mark.parametrize("classe", [Courbe, CourbeHW])
def test_choc_parallele_residuel_ordre_3(classe):
    cot0, qc = portees(classe)
    res = []
    for d in (5, 10):
        cot1 = tuple({k: v + d / 100 for k, v in q.items()} for q in qc)
        e = pnl.expliquer(PF, J0, J1, cot0, cot1, FIX, classe)
        assert abs(e["residuel"]) < 1e-3 * abs(e["delta"])
        res.append(e["residuel"])
    assert res[1] / res[0] == pytest.approx(8, rel=0.05)  # doubler le choc multiplie le résiduel par 2³


def test_flux_payes():
    s = p.Swap(date(2025, 6, 2), "2Y", 0.03, 1e6)  # premier coupon fixe payé avec le 2e variable, en juin 2026
    (bf, tf), (a, bv, tv) = s.ech.fixe[0], s.ech.variable[1]
    assert bf == bv and JOURS[0] < bf <= J1
    attendu = 1e6 * (tv * FIX(dt.add_business_days(a, -2)) - 0.03 * tf)
    assert s.flux(bf - timedelta(days=1), bf, FIX) == pytest.approx(attendu, rel=1e-14)
    assert s.flux(bf, J1, FIX) == 0
