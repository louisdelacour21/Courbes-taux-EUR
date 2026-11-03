"""Pricer de swaps EUR contre EURIBOR 6M (conventions de l'IRS de calage) : neufs, à départ décalé ou en cours de vie.

V = s N [Σ τ_j F_j Pd(t_j) − K Σ τ_i Pd(t_i)], s = +1 payeur du fixe. Les flux payés au plus tard le jour d'évaluation
sont exclus (comme QuantLib) ; un coupon variable dont le fixing (T-2) est antérieur au jour d'évaluation prend le
fixing publié, sinon le forward de la courbe 6M. P6 et Pd peuvent renvoyer des `Dual`.
"""
from datetime import date
from pathlib import Path

import pandas as pd

from courbes import dates as dt
from courbes.instruments import IRS

PORTEFEUILLE = Path(__file__).resolve().parent.parent / "data" / "portefeuille.csv"


class Swap:
    def __init__(self, debut: date, tenor: str, taux_fixe: float, notionnel: float, payeur: bool = True, nom: str = ""):
        self.ech = IRS(debut, tenor)  # même échéancier que l'IRS de calage, depuis la date de départ
        self.debut, self.tenor, self.K, self.N, self.payeur, self.nom = debut, tenor, taux_fixe, notionnel, payeur, nom

    def fixings(self, jour: date) -> list[date]:
        """Dates de fixing passées des coupons variables encore vivants."""
        return [f for a, b, _ in self.ech.variable if b > jour and (f := dt.add_business_days(a, -2)) < jour]

    def valeur(self, jour: date, P6, Pd, fixing=None, coupure: date | None = None):
        """`fixing(date)` : fixing EURIBOR 6M publié (décimal), requis pour les swaps en cours de vie.

        `coupure` : fixings publiés pour les dates antérieures à `coupure` (défaut : jour), forwards au-delà.
        """
        coupure = coupure or jour
        fixe = sum(tau * Pd(b) for b, tau in self.ech.fixe if b > jour)
        flottant = 0.0
        for a, b, tau in self.ech.variable:
            if b <= jour:
                continue
            f = dt.add_business_days(a, -2)
            flottant = flottant + tau * (fixing(f) if f < coupure else (P6(a) / P6(b) - 1) / tau) * Pd(b)
        return (1 if self.payeur else -1) * self.N * (flottant - self.K * fixe)

    def flux(self, jour0: date, jour1: date, fixing) -> float:
        """Flux nets payés dans ]jour0, jour1] (fixings tous publiés)."""
        fixe = sum(tau for b, tau in self.ech.fixe if jour0 < b <= jour1)
        flottant = sum(tau * fixing(dt.add_business_days(a, -2)) for a, b, tau in self.ech.variable if jour0 < b <= jour1)
        return (1 if self.payeur else -1) * self.N * (flottant - self.K * fixe)


def fixings_depot(cot: pd.DataFrame):
    """Hypothèse : fixing EURIBOR 6M du jour = cotation reconstituée du dépôt 6M de ce jour (les fixings sont sous
    licence EMMI). Composante construite par hypothèse, présentée comme telle.

    Fixings antérieurs aux données (trois, mi-2025, swaps en cours de vie) : première cotation disponible.
    """
    d = cot[cot.type == "DEPOT"].set_index("date").taux / 100
    return lambda jour: float(d[jour] if jour >= d.index[0] else d.iloc[0])


def lire_portefeuille(path=PORTEFEUILLE) -> list[Swap]:
    df = pd.read_csv(path, parse_dates=["debut"])
    return [Swap(r.debut.date(), r.tenor, r.taux_fixe / 100, r.notionnel, r.sens == "payeur", r.nom)
            for r in df.itertuples()]
