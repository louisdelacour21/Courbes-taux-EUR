"""Construction des courbes QuantLib de référence, partagée par les bancs (QuantLib sert aux tests seulement)."""
from datetime import date

import QuantLib as ql

from courbes import dates as dt


def q(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


def jours_du_banc(cot):
    jours = sorted(cot.date.unique())
    # un jour sur 10, plus tous les jours dont le spot est un dernier jour ouvré du mois (règle de fin de mois)
    fin_de_mois = [j for j in jours if dt.is_end_of_month(dt.add_business_days(j, 2))]
    return sorted(set(jours[::10]) | set(fin_de_mois) | {jours[-1]})


def courbe(jour: date, helpers):
    k = ql.PiecewiseLogLinearDiscount(q(jour), helpers, ql.Actual365Fixed(), [], [], ql.LogLinear(),
                                      ql.IterativeBootstrap(1e-14))
    k.enableExtrapolation()
    return k


def courbe_estr(jour: date, cotations_ois: dict):
    """OISRateHelper : ql.Estr, spot 2, paiement J+1 MF TARGET, fin de mois, pilier LastRelevantDate."""
    ql.Settings.instance().evaluationDate = q(jour)
    helpers = [ql.OISRateHelper(2, ql.Period(t), ql.QuoteHandle(ql.SimpleQuote(v / 100)), ql.Estr(),
                                paymentLag=1, paymentConvention=ql.ModifiedFollowing, paymentCalendar=ql.TARGET(),
                                endOfMonth=True, pillar=ql.Pillar.LastRelevantDate)
               for t, v in cotations_ois.items()]
    return courbe(jour, helpers), helpers


def courbe_euribor6m(jour: date, instruments, cotations: list, estr):
    """Mêmes instruments que les nôtres (liste déjà triée et dédoublonnée), actualisation sur la courbe €STR `estr`."""
    ql.Settings.instance().evaluationDate = q(jour)
    actu = ql.YieldTermStructureHandle(estr)
    helpers = []
    for i, v in zip(instruments, cotations):
        h = ql.QuoteHandle(ql.SimpleQuote(v / 100))
        if i.tenor == "6M":
            helpers.append(ql.DepositRateHelper(h, ql.Euribor6M()))
        elif "x" in i.tenor:
            helpers.append(ql.FraRateHelper(h, int(i.tenor.split("x")[0]), ql.Euribor6M()))
        else:
            helpers.append(ql.SwapRateHelper(h, ql.Period(i.tenor), ql.TARGET(), ql.Annual, ql.ModifiedFollowing,
                                             ql.Thirty360(ql.Thirty360.BondBasis), ql.Euribor6M(),
                                             ql.QuoteHandle(), ql.Period(0, ql.Days), actu, 2,
                                             ql.Pillar.LastRelevantDate, ql.Date(), True))
    return courbe(jour, helpers), helpers
