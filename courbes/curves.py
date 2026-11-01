"""Courbe d'actualisation €STR : inconnues x_k = ln P(T_k) aux piliers, interpolation log-linéaire, Newton global.

Le jacobien est analytique : la courbe renvoie des `Dual` (valeur + gradient par rapport aux x_k), propagés
exactement par les formules des instruments (différentiation automatique en mode direct).
"""
import math
from datetime import date

import numpy as np

from courbes import dates as dt
from courbes.instruments import OIS


class Dual:
    """Nombre dual v + g·ε : arithmétique exacte du premier ordre, g = gradient (vecteur numpy)."""
    __slots__ = ("v", "g")

    def __init__(self, v, g):
        self.v, self.g = v, g

    @staticmethod
    def _c(o):
        return o if isinstance(o, Dual) else Dual(o, 0.0)

    def __add__(self, o):
        o = self._c(o)
        return Dual(self.v + o.v, self.g + o.g)

    __radd__ = __add__

    def __sub__(self, o):
        o = self._c(o)
        return Dual(self.v - o.v, self.g - o.g)

    def __rsub__(self, o):
        return self._c(o) - self

    def __mul__(self, o):
        o = self._c(o)
        return Dual(self.v * o.v, self.g * o.v + o.g * self.v)

    __rmul__ = __mul__

    def __truediv__(self, o):
        o = self._c(o)
        return Dual(self.v / o.v, (self.g * o.v - o.g * self.v) / (o.v * o.v))

    def __rtruediv__(self, o):
        return self._c(o) / self


class Courbe:
    """ln P linéaire en t = ACT/365F entre (0, 0) et les piliers ; au-delà du dernier, forward constant."""

    def __init__(self, jour: date, piliers: list[date], x):
        self.jour, self.piliers = jour, list(piliers)
        self.x = np.asarray(x, dtype=float)
        self.t = np.array([0.0] + [dt.year_fraction(jour, d, "ACT/365F") for d in piliers])

    def _poids(self, d: date):
        """(i, w) : ln P(d) = (1 - w)·X[i] + w·X[i+1], X = [0, x_1, ..., x_n]."""
        t = dt.year_fraction(self.jour, d, "ACT/365F")
        if t < 0:
            raise ValueError(f"date {d} antérieure à la date de courbe {self.jour}")
        i = min(int(np.searchsorted(self.t, t, side="right")) - 1, len(self.t) - 2)
        return i, (t - self.t[i]) / (self.t[i + 1] - self.t[i])

    def ln_p(self, d: date) -> float:
        i, w = self._poids(d)
        X = np.r_[0.0, self.x]
        return (1 - w) * X[i] + w * X[i + 1]

    def P(self, d: date) -> float:
        return math.exp(self.ln_p(d))

    def P_dual(self, d: date) -> Dual:
        i, w = self._poids(d)
        X = np.r_[0.0, self.x]
        p = math.exp((1 - w) * X[i] + w * X[i + 1])
        g = np.zeros(len(self.x))
        if i > 0:
            g[i - 1] = (1 - w) * p
        g[i] = w * p
        return Dual(p, g)


def newton(jour: date, instruments: list, cotations, tol: float = 1e-13, max_iter: int = 30) -> Courbe:
    """Résout taux_k(courbe) = cotation_k (décimal) ; un pilier par instrument (dernière date pertinente).

    Départ : courbe à taux plat égal à chaque cotation. shortcut: la fiche prévoit un départ par bootstrap
    séquentiel ; inutile en log-linéaire (Newton converge en ~4 itérations), à revoir pour Hagan-West (étape 6).
    """
    piliers = [i.pilier for i in instruments]
    if any(a >= b for a, b in zip(piliers, piliers[1:])):
        raise ValueError("piliers non strictement croissants")
    q = np.asarray(cotations, dtype=float)
    c = Courbe(jour, piliers, -q * np.array([dt.year_fraction(jour, d, "ACT/365F") for d in piliers]))
    for _ in range(max_iter):
        duals = [i.taux(c.P_dual) for i in instruments]
        residus = np.array([d.v for d in duals]) - q
        c.jacobien = np.array([d.g for d in duals])  # dR/dx, réutilisé pour les buckets (étape 8)
        c.residus = residus
        if np.max(np.abs(residus)) < tol:
            return c
        c = Courbe(jour, piliers, c.x - np.linalg.solve(c.jacobien, residus))
    raise RuntimeError(f"Newton non convergé : max|R| = {np.max(np.abs(residus)):.2e}")


def courbe_estr(jour: date, cotations_ois: dict) -> Courbe:
    """Courbe €STR du jour à partir des taux OIS (en %, {ténor: taux})."""
    spot = dt.add_business_days(jour, 2)
    instruments = sorted((OIS(spot, t) for t in cotations_ois), key=lambda i: i.pilier)
    c = newton(jour, instruments, [cotations_ois[i.tenor] / 100 for i in instruments])
    c.instruments = instruments
    return c
