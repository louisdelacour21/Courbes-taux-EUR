"""Instruments de calage : dates précalculées une fois, taux implicite calculé à partir d'une fonction P(date).

P peut renvoyer des flottants ou des `Dual` (courbes/curves.py) : le même code donne alors le taux et son gradient.
"""
from datetime import date

from courbes import dates as dt


class OIS:
    """OIS €STR : spot → spot + ténor, un seul flux jusqu'à 1 an puis annuel, ACT/360, MF fin de mois, paiement J+1.

    Jambe variable d'une période = P(a)/P(b) - 1 (capitalisation €STR télescopée), payée en J+1 ouvré.
    """

    def __init__(self, spot: date, tenor: str):
        self.tenor = tenor
        fin = dt.advance(spot, tenor, "MF", eom=True)
        n, u = dt.parse_tenor(tenor)
        mois = n * 12 if u == "Y" else n if u == "M" else 0
        ech = dt.schedule(spot, fin, "1Y", "MF", eom=True) if mois > 12 else [spot, fin]
        self.periodes = [(a, b, dt.add_business_days(b, 1), dt.year_fraction(a, b, "ACT/360"))
                         for a, b in zip(ech, ech[1:])]
        self.pilier = self.periodes[-1][2]  # dernière date pertinente : dernier paiement

    def taux(self, P):
        flottant = fixe = 0.0
        for a, b, paiement, tau in self.periodes:
            p = P(paiement)
            flottant += (P(a) / P(b) - 1) * p
            fixe += tau * p
        return flottant / fixe
