"""Risques du portefeuille de swaps (data/portefeuille.csv) au dernier jour des cotations, Hagan-West et log-linéaire :
valeur, DV01, buckets, couverture, IRRBB, localité des buckets ; export des chocs pour le projet 04.

    python etudes/risque.py   →   etudes/risque.md, etudes/chocs_irrbb.yaml
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from courbes import cotations as c  # noqa: E402
from courbes import pricing as p  # noqa: E402
from courbes import risque as r  # noqa: E402
from courbes.curves import Courbe, CourbeHW  # noqa: E402


def eur(v):
    return f"{v:,.0f}".replace(",", " ")


def main():
    cot = c.lire_cotations()
    jour = cot.date.max()
    g = cot[cot.date == jour]
    o, s6 = g[g.type == "OIS"], g[g.type.isin(["DEPOT", "FRA", "IRS"])]
    ois, six = dict(zip(o.tenor, o.taux)), dict(zip(s6.type + " " + s6.tenor, s6.taux))
    fx, pf = p.fixings_depot(cot), p.lire_portefeuille()
    hors_grille = [s for s in pf if s.nom == "P10Y-2024"]

    res = {}
    for nom, K in [("Hagan-West", CourbeHW), ("Log-linéaire", Courbe)]:
        e, k = r.construire(jour, ois, six, K)
        t0 = time.perf_counter()
        v, b = r.buckets(pf, jour, e, k, fx)
        tb = time.perf_counter() - t0
        bump = [r.valeur(pf, jour, *r.construire(jour, {t: x + d for t, x in ois.items()},
                                                 {t: x + d for t, x in six.items()}, K), fx) for d in (0.01, -0.01)]
        h, B = r.couverture(jour, e, k, b)
        res[nom] = dict(v=v, b=b, tb=tb, dv01_q=(bump[0] - bump[1]) / 2, dv01_z=r.dv01_zero(pf, jour, e, k, fx),
                        h=h, residu=np.abs(b + B @ h).max(), irrbb=r.irrbb(pf, jour, e, k, fx),
                        b10=r.buckets(hors_grille, jour, e, k, fx)[1], lab=r.libelles(e, k))
    lab = res["Hagan-West"]["lab"]
    hw, ll = res["Hagan-West"], res["Log-linéaire"]

    md = [f"# Risques du portefeuille de swaps au {jour}", "",
          "Dix swaps (payeurs et receveurs, départs décalés, swaps en cours de vie avec fixing passé), "
          "`data/portefeuille.csv`. Fixings EURIBOR 6M passés : cotation DEPOT 6M reconstituée du jour de fixing "
          "(hypothèse, voir `hypotheses.md`).", "",
          "| Mesure | Hagan-West | Log-linéaire |", "|---|---:|---:|",
          f"| Valeur (EUR) | {eur(hw['v'])} | {eur(ll['v'])} |",
          f"| DV01 cotations, ±1 bp rebootstrap (EUR/bp) | {eur(hw['dv01_q'])} | {eur(ll['dv01_q'])} |",
          f"| Σ buckets (EUR/bp) | {eur(hw['b'].sum())} | {eur(ll['b'].sum())} |",
          f"| DV01 zéro, +1 bp sur les taux zéro (EUR/bp) | {eur(hw['dv01_z'])} | {eur(ll['dv01_z'])} |",
          f"| Temps des buckets (s) | {hw['tb']:.2f} | {ll['tb']:.2f} |",
          f"| Résidu de couverture max (EUR/bp) | {hw['residu']:.1e} | {ll['residu']:.1e} |", "",
          "DV01 cotations et DV01 zéro diffèrent (~4 %) : un bp sur les cotations ne décale pas les zéros d'un bp "
          "(annuité contre duration zéro, et la base €STR/6M bouge avec).", "",
          "## Buckets et couverture (Hagan-West)", "",
          "Couverture en instruments de calage au pair, notionnel payeur du fixe (négatif = receveur). "
          "Instruments dont |bucket| > 100 EUR/bp :", "",
          "| Instrument | Bucket (EUR/bp) | Notionnel de couverture (EUR) |", "|---|---:|---:|"]
    md += [f"| {lab[i]} | {hw['b'][i]:,.0f} | {eur(hw['h'][i])} |".replace(",", " ")
           for i in np.argsort(-np.abs(hw["b"])) if abs(hw["b"][i]) > 100]

    md += ["", "## IRRBB, ΔEVE (BCBS 2016, EUR, plancher EBA)", "", "| Scénario | Hagan-West | Log-linéaire |",
           "|---|---:|---:|"]
    md += [f"| {s} | {eur(hw['irrbb'][s])} | {eur(ll['irrbb'][s])} |" for s in r.SCENARIOS]
    pire = min(hw["irrbb"], key=hw["irrbb"].get)
    md += ["", f"Pire scénario : {pire} ({eur(hw['irrbb'][pire])} EUR). Chocs exportés pour le projet 04 dans "
           "`etudes/chocs_irrbb.yaml` (bp par maturité, avant plancher)."]

    md += ["", "## Localité des buckets : swap P10Y-2024 seul (payeur, 25 M€, 2,80 %, échéance 15/03/2034)", "",
           "Un swap spot de ténor coté (P10Y) a ses dates sur les piliers : ses buckets sont identiques dans les deux "
           "interpolations (IRS 10Y + OIS). Le P10Y-2024 a ses dates entre les piliers, l'interpolation compte.", "",
           "| Instrument | Hagan-West | Log-linéaire |", "|---|---:|---:|"]
    i10 = [lab.index("IRS 7Y"), lab.index("IRS 8Y")]  # piliers encadrant le 15/03/2034
    for i in range(len(lab)):
        if max(abs(hw["b10"][i]), abs(ll["b10"][i])) > 1:
            md.append(f"| {lab[i]} | {hw['b10'][i]:,.1f} | {ll['b10'][i]:,.1f} |".replace(",", " "))
    hors = {n: 1 - np.abs(x["b10"][i10]).sum() / np.abs(x["b10"]).sum() for n, x in res.items()}
    n_actifs = {n: int((np.abs(x["b10"]) > 1).sum()) for n, x in res.items()}
    md += ["", f"Part des |buckets| hors IRS 7Y et 8Y : Hagan-West {hors['Hagan-West']:.1%}, log-linéaire "
           f"{hors['Log-linéaire']:.1%} ; instruments à plus de 1 EUR/bp : {n_actifs['Hagan-West']} contre "
           f"{n_actifs['Log-linéaire']}."]

    out = Path(__file__).parent
    (out / "chocs_irrbb.yaml").write_bytes(r.chocs_yaml().encode("utf-8"))
    (out / "risque.md").write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    print(out / "risque.md")


if __name__ == "__main__":
    main()
