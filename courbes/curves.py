"""Courbes €STR (actualisation) et EURIBOR 6M (projection) : inconnues x_k = ln P(T_k) aux piliers, interpolation log-linéaire, Newton global.

Le jacobien est analytique : la courbe renvoie des `Dual` (valeur + gradient par rapport aux x_k), propagés
exactement par les formules des instruments (différentiation automatique en mode direct).
"""
import math
from datetime import date

import numpy as np

from courbes import dates as dt
from courbes.instruments import IRS, OIS, Depot


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

    def __neg__(self):
        return Dual(-self.v, -self.g)


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


def _v(z):
    return z.v if isinstance(z, Dual) else z


def _exp(z):
    if isinstance(z, Dual):
        e = math.exp(z.v)
        return Dual(e, e * z.g)
    return math.exp(z)


def _cube(z):
    return z * z * z


def primitive_g(g0, g1, x):
    """G(x) = ∫_0^x g, g = écart du forward instantané au forward discret sur un intervalle ramené à [0, 1].

    Hagan & West (2006), méthode monotone convexe : g(0) = g0, g(1) = g1, G(1) = 0 (conservation de ∫f) ; quatre
    régions selon (g0, g1). Fonctionne sur des flottants ou des `Dual` (les branches se décident sur les valeurs).
    """
    a, b = _v(g0), _v(g1)
    if a == 0 and b == 0:
        return 0.0
    if (a < 0 and -a / 2 <= b <= -2 * a) or (a > 0 and -a / 2 >= b >= -2 * a):  # (i) quadratique
        return g0 * (x - 2 * x * x + x * x * x) + g1 * (x * x * x - x * x)
    if (a < 0 and b > -2 * a) or (a > 0 and b < -2 * a):  # (ii) plat puis quadratique
        eta = (g1 + 2 * g0) / (g1 - g0)
        if x <= _v(eta):
            return g0 * x
        return g0 * x + (g1 - g0) * _cube(x - eta) / (3 * (1 - eta) * (1 - eta))
    if (a > 0 and 0 > b > -a / 2) or (a < 0 and 0 < b < -a / 2):  # (iii) quadratique puis plat
        eta = 3 * g1 / (g1 - g0)
        if x < _v(eta):
            return g1 * x + (g0 - g1) * (_cube(eta) - _cube(eta - x)) / (3 * eta * eta)
        return g1 * x + (g0 - g1) * eta / 3
    eta = g1 / (g1 + g0)  # (iv) g0 et g1 de même signe : deux quadratiques raccordées au minimum A
    A = -g0 * g1 / (g0 + g1)
    if x <= _v(eta):
        return A * x + (g0 - A) * (_cube(eta) - _cube(eta - x)) / (3 * eta * eta)
    return A * x + (g0 - A) * eta / 3 + (g1 - A) * _cube(x - eta) / (3 * (1 - eta) * (1 - eta))


class CourbeHW(Courbe):
    """Hagan-West monotone convexe sur les mêmes inconnues x_k = ln P(T_k) : forward instantané continu, ∫f conservée
    sur chaque intervalle (les DF aux piliers sont exactement exp(x_k)). Au-delà du dernier pilier : dernier forward
    discret prolongé, comme le log-linéaire et QuantLib (le forward instantané y saute de f_n à fd_n).

    shortcut: sans la contrainte de positivité de l'article (inutile en taux positifs, nuisible en taux négatifs), à
    ajouter en option si un forward négatif apparaît sur des cotations positives. Non locale : x_k influence
    les intervalles voisins via les forwards aux nœuds.
    """

    def __init__(self, jour: date, piliers: list[date], x):
        super().__init__(jour, piliers, x)
        e = np.eye(len(self.x))
        self._flottant = self._noeuds([0.0] + list(self.x))
        self._dual = self._noeuds([0.0] + [Dual(v, e[k]) for k, v in enumerate(self.x)])

    def _noeuds(self, X):
        """(X, forwards discrets fd_i sur ]t_{i-1}, t_i], forwards instantanés f_i aux nœuds)."""
        t, n = self.t, len(self.t) - 1
        fd = [None] + [(X[i - 1] - X[i]) / (t[i] - t[i - 1]) for i in range(1, n + 1)]
        f = [None] * (n + 1)
        for i in range(1, n):
            f[i] = ((t[i] - t[i - 1]) * fd[i + 1] + (t[i + 1] - t[i]) * fd[i]) / (t[i + 1] - t[i - 1])
        if n == 1:
            f[0] = f[1] = fd[1]
        else:
            f[0] = fd[1] - 0.5 * (f[1] - fd[1])
            f[n] = fd[n] - 0.5 * (f[n - 1] - fd[n])
        return X, fd, f

    def _ln(self, d: date, noeuds):
        X, fd, f = noeuds
        t = dt.year_fraction(self.jour, d, "ACT/365F")
        if t < 0:
            raise ValueError(f"date {d} antérieure à la date de courbe {self.jour}")
        n = len(self.t) - 1
        if t >= self.t[n]:
            return X[n] - fd[n] * (t - self.t[n])
        i = int(np.searchsorted(self.t, t, side="right"))  # t dans [t_{i-1}, t_i[
        h = self.t[i] - self.t[i - 1]
        x = (t - self.t[i - 1]) / h
        return X[i - 1] - fd[i] * (t - self.t[i - 1]) - h * primitive_g(f[i - 1] - fd[i], f[i] - fd[i], x)

    def ln_p(self, d: date) -> float:
        return self._ln(d, self._flottant)

    def P_dual(self, d: date) -> Dual:
        return _exp(self._ln(d, self._dual))


def newton(jour: date, instruments: list, cotations, actualisation=None, classe=Courbe, tol: float = 1e-13,
           max_iter: int = 30) -> Courbe:
    """Résout taux_k(courbe) = cotation_k (décimal) ; un pilier par instrument (dernière date pertinente).

    `actualisation` : courbe d'actualisation exogène (P(date) flottant) passée aux instruments ; None = la courbe elle-même.
    `classe` : Courbe (log-linéaire) ou CourbeHW.

    Départ en log-linéaire : courbe à taux plat égal à chaque cotation (Newton converge en ~4 itérations). Le
    log-linéaire étant local, sa solution est celle d'un bootstrap séquentiel ; elle sert de départ aux autres classes.
    """
    piliers = [i.pilier for i in instruments]
    if any(a >= b for a, b in zip(piliers, piliers[1:])):
        raise ValueError("piliers non strictement croissants")
    q = np.asarray(cotations, dtype=float)
    if classe is Courbe:
        x = -q * np.array([dt.year_fraction(jour, d, "ACT/365F") for d in piliers])
    else:
        x = newton(jour, instruments, cotations, actualisation, Courbe, tol, max_iter).x
    c = classe(jour, piliers, x)
    for _ in range(max_iter):
        duals = [i.taux(c.P_dual, actualisation) if actualisation else i.taux(c.P_dual) for i in instruments]
        residus = np.array([d.v for d in duals]) - q
        c.jacobien = np.array([d.g for d in duals])  # dR/dx, réutilisé pour les buckets (étape 8)
        c.residus = residus
        if np.max(np.abs(residus)) < tol:
            return c
        c = classe(jour, piliers, c.x - np.linalg.solve(c.jacobien, residus))
    raise RuntimeError(f"Newton non convergé : max|R| = {np.max(np.abs(residus)):.2e}")


def courbe_estr(jour: date, cotations_ois: dict, classe=Courbe) -> Courbe:
    """Courbe €STR du jour à partir des taux OIS (en %, {ténor: taux})."""
    spot = dt.add_business_days(jour, 2)
    instruments = sorted((OIS(spot, t) for t in cotations_ois), key=lambda i: i.pilier)
    c = newton(jour, instruments, [cotations_ois[i.tenor] / 100 for i in instruments], classe=classe)
    c.instruments = instruments
    return c


def courbe_euribor6m(jour: date, cotations: dict, estr: Courbe, classe=Courbe) -> Courbe:
    """Courbe de projection EURIBOR 6M, actualisée sur la courbe €STR.

    `cotations` en % : {"DEPOT 6M": r, "FRA 1x7": r, ..., "IRS 2Y": r, ...}. Un instrument dont le pilier coïncide avec
    celui d'un instrument plus court est écarté (en pratique l'IRS 2Y, même maturité que le FRA 18x24).
    """
    spot = dt.add_business_days(jour, 2)
    tous = []
    for cle, v in cotations.items():
        typ, tenor = cle.split()
        i = Depot(spot) if typ == "DEPOT" else Depot(spot, int(tenor.split("x")[0])) if typ == "FRA" else IRS(spot, tenor)
        tous.append((i.pilier, typ == "IRS", i, v))
    instruments, q, vus = [], [], set()
    for pilier, _, i, v in sorted(tous, key=lambda x: x[:2]):  # à pilier égal, le dépôt / FRA passe avant l'IRS
        if pilier not in vus:
            vus.add(pilier)
            instruments.append(i)
            q.append(v / 100)
    c = newton(jour, instruments, q, actualisation=estr.P, classe=classe)
    c.instruments = instruments
    c.cotations = q  # décimal, dans l'ordre des instruments retenus
    return c
