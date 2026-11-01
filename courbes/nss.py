"""Ajustement Nelson-Siegel-Svensson : lissage et lecture niveau / pente / courbure, jamais pricing.

y(τ) = β0 + β1 L(τ/λ1) + β2 [L(τ/λ1) − e^{−τ/λ1}] + β3 [L(τ/λ2) − e^{−τ/λ2}],  L(u) = (1 − e^{−u})/u,
taux zéro en capitalisation continue (décimal), τ en années ACT/365F.
β par moindres carrés ordinaires à (λ1, λ2) fixés ; (λ1, λ2) par grille puis least_squares (β « profilés »).

Identification : λ2 ≥ 2 λ1 (ordre de la BCE : τ1 ~ 3 ans, τ2 ~ 13 ans) et λ ≤ 30 ans. Sans ces contraintes, l'optimum
glisse souvent vers λ1 ≈ λ2 (les deux bosses deviennent colinéaires, β2 ≈ −β3 ~ ±1e3) ou vers λ → ∞ (pente et courbure
colinéaires au niveau) : même RMSE, paramètres sans signification et instables d'un jour à l'autre.
"""
import numpy as np
from scipy.optimize import least_squares

GRILLE = np.geomspace(0.1, 30.0, 16)
L_MIN, L_MAX = 0.1, 30.0


def facteurs(t, l1, l2):
    """Matrice (n, 4) des chargements [1, L1, L1 − e1, L2 − e2] ; limite τ → 0 : [1, 1, 0, 0]."""
    t = np.maximum(np.asarray(t, dtype=float), 1e-10)
    u1, u2 = t / l1, t / l2
    L1, L2 = -np.expm1(-u1) / u1, -np.expm1(-u2) / u2
    return np.column_stack([np.ones_like(t), L1, L1 - np.exp(-u1), L2 - np.exp(-u2)])


def zero(t, beta, l1, l2):
    return facteurs(t, l1, l2) @ np.asarray(beta)


def _beta(t, y, l1, l2):
    return np.linalg.lstsq(facteurs(t, l1, l2), y, rcond=None)[0]


def _lambdas(z):
    """z = (ln λ1, s) : λ2 = 2 λ1 + s (λ_max − 2 λ1), s ∈ [0, 1], soit 2 λ1 ≤ λ2 ≤ λ_max."""
    l1 = np.exp(z[0])
    return l1, 2 * l1 + z[1] * (L_MAX - 2 * l1)


def _residus(z, t, y):
    l1, l2 = _lambdas(z)
    return facteurs(t, l1, l2) @ _beta(t, y, l1, l2) - y


class NSS:
    def __init__(self, beta, l1, l2, rmse):
        self.beta, self.l1, self.l2, self.rmse = np.asarray(beta), l1, l2, rmse

    def zero(self, t):
        return zero(t, self.beta, self.l1, self.l2)

    @property
    def niveau(self):  # taux zéro infini
        return self.beta[0]

    @property
    def pente(self):  # long − court : y(∞) − y(0) = −β1
        return -self.beta[1]


def ajuster(t, y) -> NSS:
    """Ajuste NSS aux zéros y (décimal) aux maturités t (années)."""
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    grille = [(np.log(a), (b - 2 * a) / (L_MAX - 2 * a)) for a in GRILLE for b in GRILLE if 2 * a <= b]
    depart = min(grille, key=lambda z: np.sum(_residus(z, t, y) ** 2))
    r = least_squares(_residus, depart, args=(t, y), bounds=([np.log(L_MIN), 0.0], [np.log(L_MAX / 2), 1.0]),
                      xtol=1e-15, ftol=1e-15, gtol=1e-15)
    l1, l2 = _lambdas(r.x)
    return NSS(_beta(t, y, l1, l2), l1, l2, float(np.sqrt(np.mean(r.fun ** 2))))


def ajuster_courbe(courbe) -> NSS:
    """NSS ajusté aux zéros bootstrapés de la courbe, à ses piliers."""
    t = courbe.t[1:]
    return ajuster(t, -courbe.x / t)
