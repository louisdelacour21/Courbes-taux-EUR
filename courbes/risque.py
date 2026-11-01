"""Risques d'un portefeuille de swaps sur les deux courbes : buckets par jacobien, DV01, couverture, scénarios IRRBB.

Inconnues x = [x_€STR, x_6M]. Le jacobien global J = ∂R/∂x est triangulaire par blocs (la courbe 6M dépend de l'€STR
par l'actualisation, pas l'inverse). Buckets : ∂V/∂q = (∂V/∂x) J⁻¹, en EUR par bp de cotation.
"""
import math

import numpy as np

from courbes.curves import CourbeHW, Dual, courbe_estr, courbe_euribor6m
from courbes.instruments import IRS, OIS, Depot

BP = 1e-4


def construire(jour, ois: dict, six: dict, classe=CourbeHW):
    """(courbe €STR, courbe 6M) à partir des cotations en % ({ténor: taux} et {"TYPE ténor": taux})."""
    estr = courbe_estr(jour, ois, classe)
    return estr, courbe_euribor6m(jour, six, estr, classe)


def cle(i) -> str:
    """Libellé de cotation d'un instrument de calage, au format des dictionnaires de `construire`."""
    if isinstance(i, OIS):
        return i.tenor
    if isinstance(i, IRS):
        return f"IRS {i.tenor}"
    return f"DEPOT {i.tenor}" if i.tenor == "6M" else f"FRA {i.tenor}"


def _plonger(P_dual, debut: int, n: int):
    """P renvoyant des Dual dont le gradient est placé à la position `debut` d'un vecteur de taille n."""
    def P(d):
        z = P_dual(d)
        g = np.zeros(n)
        g[debut:debut + len(z.g)] = z.g
        return Dual(z.v, g)
    return P


def jacobien(estr, six):
    """(J, P6, Pd) : jacobien global et fonctions d'actualisation duales sur x = [x_€STR, x_6M]."""
    nd, n = len(estr.x), len(estr.x) + len(six.x)
    Pd, P6 = _plonger(estr.P_dual, 0, n), _plonger(six.P_dual, nd, n)
    J = np.array([i.taux(Pd).g for i in estr.instruments] + [i.taux(P6, Pd).g for i in six.instruments])
    return J, P6, Pd


def libelles(estr, six) -> list[str]:
    return [f"OIS {i.tenor}" for i in estr.instruments] + [cle(i) for i in six.instruments]


def _grad(v, n):
    return v.g if isinstance(v, Dual) else np.zeros(n)  # swap échu : valeur 0, sans gradient


def buckets(swaps, jour, estr, six, fixing=None):
    """(valeur, buckets) du portefeuille : buckets[k] = ∂V/∂q_k en EUR par bp, dans l'ordre de `libelles`."""
    J, P6, Pd = jacobien(estr, six)
    v = sum((s.valeur(jour, P6, Pd, fixing) for s in swaps), Dual(0.0, np.zeros(len(J))))
    return v.v, np.linalg.solve(J.T, v.g) * BP


def dv01_zero(swaps, jour, estr, six, fixing=None) -> float:
    """∂V pour +1 bp sur les taux zéro (continus, ACT/365F) des deux courbes : x_k → x_k − 1 bp · t_k.

    Exact au premier ordre pour les deux interpolations : le choc décale tous les forwards de 1 bp.
    """
    _, P6, Pd = jacobien(estr, six)
    t = np.r_[estr.t[1:], six.t[1:]]
    v = sum((s.valeur(jour, P6, Pd, fixing) for s in swaps), Dual(0.0, np.zeros(len(t))))
    return float(v.g @ (-BP * t))


def valeur(swaps, jour, estr, six, fixing=None) -> float:
    return sum(s.valeur(jour, six.P, estr.P, fixing) for s in swaps)


def couverture(jour, estr, six, delta):
    """Notionnels h des instruments de calage (payeurs du fixe, au pair) qui annulent les buckets : h = −B⁻¹δ.

    B[k, j] = bucket k d'un notionnel unitaire de l'instrument j. Au pair, B est diagonale (l'instrument j ne dépend que
    de sa cotation), égale à son annuité × 1 bp ; elle est calculée sans le supposer.
    """
    J, P6, Pd = jacobien(estr, six)
    q = estr.cotations + six.cotations
    G = []
    for i, k in zip(estr.instruments + six.instruments, q):
        taux = i.taux(Pd) if isinstance(i, OIS) else i.taux(P6, Pd)
        G.append(((taux - k) * i.annuite(Pd)).g)
    B = np.linalg.solve(J.T, np.array(G).T) * BP
    return -np.linalg.solve(B, delta), B


# IRRBB, BCBS 2016 (EUR) : chocs en bp sur les taux zéro, t en années
CHOCS = {"parallele_haut": 200.0, "parallele_bas": -200.0, "court": 250.0, "long": 100.0}
SCENARIOS = ["parallele_haut", "parallele_bas", "court_haut", "court_bas", "pentification", "aplatissement"]


def choc_bp(scenario: str, t: float) -> float:
    court = CHOCS["court"] * math.exp(-t / 4)
    long = CHOCS["long"] * (1 - math.exp(-t / 4))
    return {"parallele_haut": CHOCS["parallele_haut"], "parallele_bas": CHOCS["parallele_bas"],
            "court_haut": court, "court_bas": -court,
            "pentification": -0.65 * court + 0.9 * long, "aplatissement": 0.8 * court - 0.6 * long}[scenario]


def plancher_bp(t: float) -> float:
    """Plancher EBA post-choc : −150 bp au jour le jour, +3 bp par an, jusqu'à 0."""
    return min(-150.0 + 3.0 * t, 0.0)


def choquer(courbe, scenario: str):
    """Courbe de même classe aux taux zéro choqués aux piliers (interpolation inchangée).

    Plancher : r' = max(r + Δ, min(r, plancher)) — un taux observé déjà sous le plancher est conservé.
    """
    t = courbe.t[1:]
    z = -courbe.x / t
    zc = np.array([max(r + choc_bp(scenario, u) * BP, min(r, plancher_bp(u) * BP)) for r, u in zip(z, t)])
    return type(courbe)(courbe.jour, courbe.piliers, -zc * t)


def irrbb(swaps, jour, estr, six, fixing=None) -> dict:
    """ΔEVE (EUR) par scénario : même choc sur les taux zéro des deux courbes, revalorisation complète."""
    v0 = valeur(swaps, jour, estr, six, fixing)
    return {s: valeur(swaps, jour, choquer(estr, s), choquer(six, s), fixing) - v0 for s in SCENARIOS}


GRILLE = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]


def chocs_yaml(grille=GRILLE) -> str:
    """Chocs IRRBB au format scénarios du projet 04 (YAML écrit à la main, pas de dépendance) : choc en bp du taux
    zéro par maturité en années, avant plancher (le plancher dépend du niveau de la courbe, il s'applique au moment
    du choc)."""
    lignes = ["# Chocs de taux IRRBB (BCBS 2016, EUR), en bp sur les taux zéro, par maturité (années).",
              "# Plancher EBA post-choc à appliquer : max(r + choc, min(r, -150 + 3 t)) bp, plafonné à 0.",
              "scenarios:"]
    for s in SCENARIOS:
        lignes += [f"  irrbb_{s}:", "    type: hypothetique", "    facteur: EUR_zero", "    chocs_bp:"]
        lignes += [f"      {u}: {choc_bp(s, u):.4f}" for u in grille]
    return "\n".join(lignes) + "\n"
