"""Synthèse du matin du portefeuille : valeur, DV01, top 3 piliers, PnL expliqué de la veille, alertes, temps de calcul.

    python -m courbes.synthese [AAAA-MM-JJ]
"""
import sys
import time
from datetime import date

import numpy as np

from courbes import cotations as c
from courbes import pnl
from courbes import pricing as p
from courbes import risque as r
from courbes.curves import CourbeHW

SEUIL_RESIDUEL = 0.10  # part du PnL de la veille
SEUIL_RESIDUEL_EUR = 10_000.0
SEUIL_ISOLE_BP = 2.0  # écart du mouvement d'une cotation à celui de ses voisines (saut de base)


def eur(x: float) -> str:
    return f"{round(x):,}".replace(",", " ")  # entier : pas de « -0 »


def synthese(jour: date | None = None, classe=CourbeHW) -> dict:
    t0 = time.perf_counter()
    cot = c.lire_cotations()
    jours = sorted(cot.date.unique())
    jour = jour or jours[-1]
    veille = jours[jours.index(jour) - 1]
    pf, fx = p.lire_portefeuille(), p.fixings_depot(cot)
    q0, q1 = c.du_jour(cot, veille), c.du_jour(cot, jour)

    e, k = r.construire(jour, *q1, classe)
    v, b = r.buckets(pf, jour, e, k, fx)
    noms = r.libelles(e, k)
    top = [(noms[i], float(b[i])) for i in np.argsort(-np.abs(b))[:3]]
    expl = pnl.expliquer(pf, veille, jour, q0, q1, fx, classe)

    alertes = []
    if abs(expl["residuel"]) > max(SEUIL_RESIDUEL * abs(expl["total"]), SEUIL_RESIDUEL_EUR):
        alertes.append(f"résiduel de la veille {eur(expl['residuel'])} EUR pour un PnL de {eur(expl['total'])} EUR")
    for n, prefixe in ((0, "OIS "), (1, "")):
        cles = list(q1[n])
        d = np.array([(q1[n][t] - q0[n][t]) * 100 for t in cles])
        voisins = [np.mean([d[j] for j in (i - 1, i + 1) if 0 <= j < len(d)]) for i in range(len(d))]
        alertes += [f"{prefixe}{t} a bougé de {d[i]:+.1f} bp contre {voisins[i]:+.1f} bp pour ses voisines"
                    for i, t in enumerate(cles) if abs(d[i] - voisins[i]) > SEUIL_ISOLE_BP]
    return {"jour": jour, "veille": veille, "valeur": v, "dv01": float(b.sum()), "top3": top, "pnl": expl,
            "alertes": alertes, "duree": time.perf_counter() - t0}


def texte(s: dict) -> str:
    lignes = [f"Synthèse du {s['jour']} (veille {s['veille']}), Hagan-West, cotations reconstituées",
         f"Valeur du portefeuille : {eur(s['valeur'])} EUR ; DV01 (somme des buckets) : {eur(s['dv01'])} EUR/bp",
         "Top 3 piliers : " + " ; ".join(f"{n} {eur(x)} EUR/bp" for n, x in s["top3"]),
         "PnL de la veille : " + " ; ".join(f"{k} {eur(x)}" for k, x in s["pnl"].items()) + " (EUR)",
         "Alertes : " + ("; ".join(s["alertes"]) if s["alertes"] else "aucune"),
         f"Temps de calcul : {s['duree']:.1f} s"]
    return "\n".join(lignes)


if __name__ == "__main__":
    print(texte(synthese(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)))
