"""Banc QuantLib de la courbe €STR : mêmes cotations, mêmes conventions, écarts < 1e-10 exigés.

QuantLib : OISRateHelper (ql.Estr, spot 2, paiement J+1 MF TARGET, fin de mois, pilier LastRelevantDate),
PiecewiseLogLinearDiscount en ACT/365F, précision du bootstrap 1e-14.
"""
import random
from datetime import timedelta

import QuantLib as ql
import pytest

from courbes import cotations as c
from courbes import dates as dt
from courbes.curves import courbe_estr
from courbes.instruments import OIS
from ql_banc import courbe_estr as courbe_ql, jours_du_banc, q

TOL = 1e-10
ALEA = random.Random(20261104)


COT = c.lire_cotations()


@pytest.mark.parametrize("jour", jours_du_banc(COT), ids=str)
def test_courbe_estr_identique_a_quantlib(jour):
    g = COT[(COT.date == jour) & (COT.type == "OIS")]
    cot = dict(zip(g.tenor, g.taux))
    nous = courbe_estr(jour, cot)
    kql, helpers = courbe_ql(jour, cot)

    # piliers
    assert [h.pillarDate() for h in helpers] == [q(d) for d in nous.piliers]
    # facteurs d'actualisation sur 500 dates, jusqu'à 40 ans (au-delà du dernier pilier : extrapolation)
    for _ in range(500):
        d = jour + timedelta(days=ALEA.randint(0, 40 * 365))
        assert abs(nous.P(d) - kql.discount(q(d))) < TOL, d
    # taux au pair des instruments de calage, évalués par QuantLib sur sa courbe
    for h, i in zip(helpers, nous.instruments):
        assert abs(h.impliedQuote() - i.taux(nous.P)) < TOL, i.tenor
    # 200 OIS aléatoires : départ décalé jusqu'à 5 ans, ténor de 1 semaine à 30 ans
    projection = ql.YieldTermStructureHandle(kql)
    spot = dt.add_business_days(jour, 2)
    for _ in range(200):
        debut = dt.add_business_days(spot, ALEA.randint(0, 5 * 252))
        tenor = ALEA.choice(["1W", "3W", "1M", "5M", "11M", "1Y", "13M", "18M", "2Y", "7Y", "10Y", "17Y", "30Y"])
        sw = ql.MakeOIS(ql.Period(tenor), ql.Estr(projection), 0.0, effectiveDate=q(debut), paymentLag=1,
                        paymentAdjustmentConvention=ql.ModifiedFollowing, paymentCalendar=ql.TARGET(),
                        endOfMonth=True, discountingTermStructure=projection)
        assert abs(sw.fairRate() - OIS(debut, tenor).taux(nous.P)) < TOL, (debut, tenor)
