"""Pricer, buckets, couverture et IRRBB : NPV identiques à QuantLib, buckets = bumps, portefeuille couvert à buckets nuls."""
import numpy as np
import QuantLib as ql
import pytest

from courbes import cotations as c
from courbes import dates as dt
from courbes import pricing as p
from courbes import risque as r
from courbes.curves import Courbe, CourbeHW
from courbes.instruments import IRS
from ql_banc import courbe_estr as estr_ql, courbe_euribor6m as euribor6m_ql, q

COT = c.lire_cotations()
JOUR = COT.date.max()
G = COT[COT.date == JOUR]
OIS = dict(zip(G[G.type == "OIS"].tenor, G[G.type == "OIS"].taux))
SIX = {f"{x.type} {x.tenor}": x.taux for x in G[G.type.isin(["DEPOT", "FRA", "IRS"])].itertuples()}
FIX = p.fixings_depot(COT)
PF = p.lire_portefeuille()


@pytest.fixture(scope="module", params=[Courbe, CourbeHW], ids=["log-lineaire", "hagan-west"])
def courbes(request):
    return request.param, *r.construire(JOUR, OIS, SIX, request.param)


def test_swap_au_pair_vaut_zero(courbes):
    _, estr, six = courbes
    spot = dt.add_business_days(JOUR, 2)
    for tenor in ["2Y", "7Y", "10Y", "30Y"]:
        s = p.Swap(spot, tenor, IRS(spot, tenor).taux(six.P, estr.P), 1e8)
        assert abs(s.valeur(JOUR, six.P, estr.P)) < 1e-10 * s.N


def test_npv_du_portefeuille_identiques_a_quantlib(courbes):
    classe, estr, six = courbes
    kestr, _ = estr_ql(JOUR, OIS, hw=classe is CourbeHW)
    k6, _ = euribor6m_ql(JOUR, six.instruments, [x * 100 for x in six.cotations], kestr, hw=classe is CourbeHW)
    idx = ql.Euribor6M(ql.YieldTermStructureHandle(k6))
    moteur = ql.DiscountingSwapEngine(ql.YieldTermStructureHandle(kestr))
    try:
        for s in PF:
            for f in s.fixings(JOUR):
                idx.addFixing(q(f), FIX(f), True)
            sw = ql.MakeVanillaSwap(ql.Period(s.tenor), idx, s.K, ql.Period(0, ql.Days), effectiveDate=q(s.debut),
                                    nominal=s.N, swapType=ql.Swap.Payer if s.payeur else ql.Swap.Receiver,
                                    fixedLegTenor=ql.Period(1, ql.Years),
                                    fixedLegDayCount=ql.Thirty360(ql.Thirty360.BondBasis),
                                    fixedLegConvention=ql.ModifiedFollowing,
                                    fixedLegTerminationDateConvention=ql.ModifiedFollowing,
                                    fixedLegEndOfMonth=True, floatingLegEndOfMonth=True, pricingEngine=moteur)
            assert abs(sw.NPV() - s.valeur(JOUR, six.P, estr.P, FIX)) < 1e-10 * s.N, s.nom
    finally:
        ql.IndexManager.instance().clearHistories()


def _valeur_choquee(classe, cle, h):
    """Valeur du portefeuille après un choc h (en %) sur la cotation `cle` (libellé de `risque.libelles`)."""
    ois, six = dict(OIS), dict(SIX)
    if cle.startswith("OIS "):
        ois[cle[4:]] += h
    else:
        six[cle] += h
    return r.valeur(PF, JOUR, *r.construire(JOUR, ois, six, classe), FIX)


def test_buckets_egaux_aux_bumps(courbes):
    """Choc central de 0,01 bp. Hagan-West n'est pas dérivable aux frontières de régions : écart relatif ~1e-5."""
    classe, estr, six = courbes
    v, b = r.buckets(PF, JOUR, estr, six, FIX)
    assert abs(v - r.valeur(PF, JOUR, estr, six, FIX)) < 1e-6
    tol = 1e-7 if classe is Courbe else 1e-4
    lab = r.libelles(estr, six)
    for cle in ["OIS 1Y", "OIS 10Y", "OIS 30Y", "DEPOT 6M", "FRA 6x12", "IRS 5Y", "IRS 10Y", "IRS 30Y"]:
        h = 1e-4
        bump = (_valeur_choquee(classe, cle, h) - _valeur_choquee(classe, cle, -h)) / (2 * h) / 100
        assert abs(b[lab.index(cle)] - bump) < tol * np.abs(b).max(), cle


def test_somme_des_buckets_egale_dv01_parallele(courbes):
    classe, estr, six = courbes
    _, b = r.buckets(PF, JOUR, estr, six, FIX)
    up = r.valeur(PF, JOUR, *r.construire(JOUR, {k: x + .01 for k, x in OIS.items()},
                                           {k: x + .01 for k, x in SIX.items()}, classe), FIX)
    dn = r.valeur(PF, JOUR, *r.construire(JOUR, {k: x - .01 for k, x in OIS.items()},
                                           {k: x - .01 for k, x in SIX.items()}, classe), FIX)
    assert abs(b.sum() - (up - dn) / 2) < 1e-3 * abs(b.sum())


def test_dv01_zero_egal_au_bump(courbes):
    _, estr, six = courbes
    def decale(k, h):
        return type(k)(k.jour, k.piliers, k.x - h * k.t[1:])
    up = r.valeur(PF, JOUR, decale(estr, 1e-6), decale(six, 1e-6), FIX)
    dn = r.valeur(PF, JOUR, decale(estr, -1e-6), decale(six, -1e-6), FIX)
    assert abs(r.dv01_zero(PF, JOUR, estr, six, FIX) - (up - dn) / 2e-6 * 1e-4) < 1e-6 * abs((up - dn) / 2e-2)


def test_portefeuille_couvert_a_buckets_nuls(courbes):
    _, estr, six = courbes
    _, b = r.buckets(PF, JOUR, estr, six, FIX)
    h, B = r.couverture(JOUR, estr, six, b)
    assert np.abs(B - np.diag(np.diag(B))).max() < 1e-12 * np.abs(B).max()  # au pair, chaque instrument ne voit que sa cotation
    assert np.abs(b + B @ h).max() < 1e-9 * np.abs(b).max()
    # contrôle indépendant : les notionnels de couverture d'un swap 10Y payeur se concentrent sur l'IRS 10Y
    spot = dt.add_business_days(JOUR, 2)
    s = p.Swap(spot, "10Y", 0.03, 1e7)
    h10, _ = r.couverture(JOUR, estr, six, r.buckets([s], JOUR, estr, six)[1])
    assert abs(h10[r.libelles(estr, six).index("IRS 10Y")] + 1e7) < 1e-6 * 1e7


def test_chocs_irrbb():
    assert r.choc_bp("court_haut", 0) == 250 and abs(r.choc_bp("pentification", 0) + 162.5) < 1e-12
    assert abs(r.choc_bp("pentification", 1e3) - 90) < 1e-9 and abs(r.choc_bp("aplatissement", 1e3) + 60) < 1e-9
    assert r.plancher_bp(0) == -150 and r.plancher_bp(10) == -120 and r.plancher_bp(60) == 0


def test_choc_parallele_et_plancher():
    piliers = [JOUR.replace(year=JOUR.year + n) for n in (1, 5, 30)]
    t = Courbe(JOUR, piliers, [0, 0, 0]).t[1:]
    k = Courbe(JOUR, piliers, -0.01 * t)  # zéros à 1 %
    z = lambda c: -c.x / c.t[1:]
    assert np.allclose(z(r.choquer(k, "parallele_haut")), 0.03, rtol=0, atol=1e-15)
    # −200 bp sur 1 % : −1 %, au-dessus du plancher à 1 et 5 ans (−147 et −135 bp) ; à 30 ans plancher ≈ −60 bp
    attendu = [-0.01, -0.01, r.plancher_bp(t[2]) * 1e-4]
    assert np.allclose(z(r.choquer(k, "parallele_bas")), attendu, rtol=0, atol=1e-15)
    bas = Courbe(JOUR, piliers, 0.02 * t)  # zéros à −2 %, déjà sous le plancher : conservés
    assert np.allclose(z(r.choquer(bas, "parallele_bas")), -0.02, rtol=0, atol=1e-15)


def test_export_chocs_projet_04():
    yaml = pytest.importorskip("yaml")
    s = yaml.safe_load(r.chocs_yaml())["scenarios"]
    assert len(s) == 6 and s["irrbb_parallele_bas"]["chocs_bp"][10] == -200
    assert s["irrbb_court_haut"]["chocs_bp"][2] == pytest.approx(r.choc_bp("court_haut", 2), abs=1e-4)
