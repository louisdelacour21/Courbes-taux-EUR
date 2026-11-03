"""Banc QuantLib de la courbe EURIBOR 6M : mêmes cotations, même courbe €STR d'actualisation, écarts < 1e-10.

QuantLib : DepositRateHelper / FraRateHelper sur ql.Euribor6M, SwapRateHelper (fixe annuel MF 30/360 Bond Basis,
fin de mois, actualisation exogène €STR), PiecewiseLogLinearDiscount en ACT/365F, précision 1e-14.
"""
import random
from datetime import timedelta

import QuantLib as ql
import pytest

from courbes import cotations as c
from courbes import dates as dt
from courbes.curves import courbe_estr, courbe_euribor6m, instrument_6m
from courbes.instruments import IRS
from ql_banc import courbe_estr as estr_ql, courbe_euribor6m as euribor6m_ql, jours_du_banc, q

TOL = 1e-10
ALEA = random.Random(20261105)
COT = c.lire_cotations()


@pytest.mark.parametrize("jour", jours_du_banc(COT), ids=str)
def test_courbe_euribor6m_identique_a_quantlib(jour):
    g = COT[COT.date == jour]
    ois = g[g.type == "OIS"]
    p6 = g[g.type.isin(["DEPOT", "FRA", "IRS"])]
    estr = courbe_estr(jour, dict(zip(ois.tenor, ois.taux)))
    nous = courbe_euribor6m(jour, dict(zip(p6.type + " " + p6.tenor, p6.taux)), estr)
    kestr, _ = estr_ql(jour, dict(zip(ois.tenor, ois.taux)))
    k6, helpers = euribor6m_ql(jour, nous.instruments, [r * 100 for r in nous.cotations], kestr)

    assert [h.pillarDate() for h in helpers] == [q(d) for d in nous.piliers]
    for _ in range(500):
        d = jour + timedelta(days=ALEA.randint(0, 40 * 365))
        assert abs(nous.P(d) - k6.discount(q(d))) < TOL, d
    for h, i in zip(helpers, nous.instruments):
        assert abs(h.impliedQuote() - i.taux(nous.P, estr.P)) < TOL, i.tenor

    # 200 swaps aléatoires contre EURIBOR 6M : départ décalé jusqu'à 5 ans, ténor de 1 à 30 ans
    projection, actu = ql.YieldTermStructureHandle(k6), ql.YieldTermStructureHandle(kestr)
    spot = dt.add_business_days(jour, 2)
    for _ in range(200):
        debut = dt.add_business_days(spot, ALEA.randint(0, 5 * 252))
        tenor = ALEA.choice(["1Y", "18M", "2Y", "3Y", "5Y", "7Y", "10Y", "13Y", "17Y", "20Y", "30Y"])
        sw = ql.MakeVanillaSwap(ql.Period(tenor), ql.Euribor6M(projection), 0.0, ql.Period(0, ql.Days),
                                effectiveDate=q(debut), fixedLegTenor=ql.Period(1, ql.Years),
                                fixedLegDayCount=ql.Thirty360(ql.Thirty360.BondBasis),
                                fixedLegConvention=ql.ModifiedFollowing,
                                fixedLegTerminationDateConvention=ql.ModifiedFollowing,
                                fixedLegEndOfMonth=True, floatingLegEndOfMonth=True,
                                discountingTermStructure=actu)
        assert abs(sw.fairRate() - IRS(debut, tenor).taux(nous.P, estr.P)) < TOL, (debut, tenor)


def test_irs_2y_ecarte_meme_si_son_pilier_differe_d_un_jour():
    """Sur 33 jours, la fin du FRA 18x24 et celle de l'IRS 2Y diffèrent d'un jour : garder les deux rend J quasi singulier."""
    piliers = lambda j, k: instrument_6m(dt.add_business_days(j, 2), k).pilier  # noqa: E731
    jour = next(j for j in sorted(COT.date.unique()) if piliers(j, "FRA 18x24") != piliers(j, "IRS 2Y"))
    g = COT[COT.date == jour]
    ois, p6 = g[g.type == "OIS"], g[g.type.isin(["DEPOT", "FRA", "IRS"])]
    estr = courbe_estr(jour, dict(zip(ois.tenor, ois.taux)))
    six = courbe_euribor6m(jour, dict(zip(p6.type + " " + p6.tenor, p6.taux)), estr)
    assert not any(isinstance(i, IRS) and i.tenor == "2Y" for i in six.instruments)
    assert min((b - a).days for a, b in zip(six.piliers, six.piliers[1:])) > 5
