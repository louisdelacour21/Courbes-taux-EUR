"""Instruments de calage : dates précalculées une fois, taux implicite calculé à partir d'une fonction P(date).

P peut renvoyer des flottants ou des `Dual` (courbes/curves.py) : le même code donne alors le taux et son gradient.
"""
from datetime import date, timedelta

from courbes import dates as dt


def maturite(spot: date, tenor: str) -> date:
    """Maturité NON ajustée d'un swap (spot + ténor), point de départ de l'échéancier à rebours (ql.MakeOIS).

    Règle de fin de mois : spot = dernier jour ouvré du mois → maturité au dernier jour du mois.
    """
    n, u = dt.parse_tenor(tenor)
    if u == "W":
        return spot + timedelta(weeks=n)
    fin = dt.add_months(spot, n * 12 if u == "Y" else n)
    return dt.last_day_of_month(fin) if dt.is_end_of_month(spot) else fin


class OIS:
    """OIS €STR : spot → spot + ténor, un seul flux jusqu'à 1 an puis annuel, ACT/360, MF fin de mois, paiement J+1.

    Jambe variable d'une période = P(a)/P(b) - 1 (capitalisation €STR télescopée), payée en J+1 ouvré.
    """

    def __init__(self, spot: date, tenor: str):
        self.tenor = tenor
        n, u = dt.parse_tenor(tenor)
        if u == "D":
            raise ValueError("OIS : ténor en semaines, mois ou années")
        # jusqu'à 1 an, la génération annuelle à rebours ne donne qu'une période
        ech = dt.schedule(spot, maturite(spot, tenor), "1Y", "MF", eom=True)
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

    def annuite(self, Pd):
        return sum(tau * Pd(paiement) for _, _, paiement, tau in self.periodes)


class Depot:
    """Dépôt / FRA EURIBOR 6M : spot + m mois → + 6M, ACT/360, MF fin de mois. Taux = forward simple de la courbe 6M."""

    def __init__(self, spot: date, debut_mois: int = 0):
        self.tenor = f"{debut_mois}x{debut_mois + 6}" if debut_mois else "6M"
        self.debut = dt.advance(spot, f"{debut_mois}M", "MF", eom=True) if debut_mois else spot
        self.fin = dt.advance(self.debut, "6M", "MF", eom=True)
        self.tau = dt.year_fraction(self.debut, self.fin, "ACT/360")
        self.pilier = self.fin

    def taux(self, P6, Pd=None):
        return (P6(self.debut) / P6(self.fin) - 1) / self.tau

    def annuite(self, Pd):
        return self.tau * Pd(self.fin)


class IRS:
    """Swap contre EURIBOR 6M : fixe annuel 30/360, variable semestriel ACT/360, MF fin de mois, à rebours.

    Coupon variable « au pair » (réglage par défaut de QuantLib) : forward 6M sur la période de calcul, payé en fin
    de période et actualisé sur la courbe Pd (€STR, CSA cash EUR).
    """

    def __init__(self, spot: date, tenor: str):
        self.tenor = tenor
        fin = maturite(spot, tenor)
        f = dt.schedule(spot, fin, "1Y", "MF", eom=True)
        v = dt.schedule(spot, fin, "6M", "MF", eom=True)
        self.fixe = [(b, dt.year_fraction(a, b, "30/360")) for a, b in zip(f, f[1:])]
        self.variable = [(a, b, dt.year_fraction(a, b, "ACT/360")) for a, b in zip(v, v[1:])]
        self.pilier = v[-1]

    def taux(self, P6, Pd=None):
        Pd = Pd or P6
        flottant = sum((P6(a) / P6(b) - 1) * Pd(b) for a, b, _ in self.variable)
        return flottant / self.annuite(Pd)

    def annuite(self, Pd):
        return sum(tau * Pd(b) for b, tau in self.fixe)
