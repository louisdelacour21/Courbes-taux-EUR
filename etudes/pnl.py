"""PnL explain quotidien du portefeuille (data/portefeuille.csv) sur toute l'année de cotations, Hagan-West.

Marché synthétique : cotations reconstituées et bruitées, fixings reconstitués. L'étude valide la mécanique de
décomposition, pas un comportement de marché.

    python etudes/pnl.py   →   etudes/pnl.md, etudes/pnl_serie.csv
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from courbes import cotations as c  # noqa: E402
from courbes import pricing as p  # noqa: E402
from courbes import pnl  # noqa: E402
from courbes.cotations import SAUT  # noqa: E402
from courbes.curves import Courbe  # noqa: E402

COMPOSANTES = ["portage", "fixings", "delta", "gamma", "residuel"]
eur = lambda x: f"{x:,.0f}".replace(",", " ")  # noqa: E731
pct = lambda x, n=1: f"{x:.{n}%}".replace(".", ",")  # noqa: E731


def main():
    cot = c.lire_cotations()
    jours = sorted(cot.date.unique())
    pf, fix = p.lire_portefeuille(), p.fixings_depot(cot)

    def cotations(jour):
        g = cot[cot.date == jour]
        o, s6 = g[g.type == "OIS"], g[g.type.isin(["DEPOT", "FRA", "IRS"])]
        return dict(zip(o.tenor, o.taux)), dict(zip(s6.type + " " + s6.tenor, s6.taux))

    t0, lignes, temoin = time.perf_counter(), [], []
    for j0, j1 in zip(jours, jours[1:]):
        lignes.append({"jour": j1, **pnl.expliquer(pf, j0, j1, cotations(j0), cotations(j1), fix)})
    duree = time.perf_counter() - t0
    for j0, j1 in zip(jours, jours[1:]):  # témoin log-linéaire : V lisse en les cotations
        temoin.append(pnl.expliquer(pf, j0, j1, cotations(j0), cotations(j1), fix, Courbe)["residuel"])
    df = pd.DataFrame(lignes)
    df.assign(residuel_loglin=temoin).round(2).to_csv(Path(__file__).with_name("pnl_serie.csv"), index=False)
    ll = pd.Series(temoin).abs()

    a = df[["total"] + COMPOSANTES].abs()
    part = df.residuel.abs() / df.total.abs()
    saut = df[df.jour.isin([j for j in jours if j >= SAUT["debut"]][: SAUT["jours"] + 1])]
    md = [f"# PnL explain quotidien, {df.jour.min()} → {df.jour.max()} ({len(df)} jours)", "",
          "**Marché synthétique** : cotations reconstituées depuis la BCE et bruitées (0,2 à 0,5 bp), fixings EURIBOR 6M "
          "reconstitués (cotation DEPOT 6M du jour). La composante fixings est construite par hypothèse. Ce résultat "
          "valide la mécanique de décomposition, pas un comportement de marché.", "",
          "| Composante | Moyenne (EUR) | Moyenne des valeurs absolues (EUR) | Max absolu (EUR) |", "|---|---:|---:|---:|"]
    md += [f"| {k} | {eur(df[k].mean())} | {eur(a[k].mean())} | {eur(a[k].max())} |" for k in ["total"] + COMPOSANTES]
    pire = a.residuel.idxmax()
    md += ["", f"- Résiduel moyen en valeur absolue : {pct(a.residuel.mean() / a.total.mean(), 2)} du PnL moyen en valeur "
           f"absolue ; médiane jour par jour de |résiduel| / |PnL| : {pct(part.median(), 2)} ; "
           f"variance expliquée 1 − var(résiduel) / var(PnL) : {pct(1 - df.residuel.var() / df.total.var(), 4)}.",
           f"- Pire jour : {df.jour[pire]} (résiduel {eur(df.residuel[pire])} EUR, PnL {eur(df.total[pire])} EUR).",
           f"- **Origine du résiduel** : la non-dérivabilité de Hagan-West. Sa monotone convexe change de région quand "
           "les cotations bougent, V n'est pas lisse et le développement au premier ordre décroche (le 2026-08-06, la "
           "pente le long du chemin q_c → q1 passe de −54 610 à +9 128 EUR pour un mouvement d'environ 1 bp). Témoin "
           f"log-linéaire, mêmes jours : |résiduel| moyen {eur(ll.mean())} EUR, max {eur(ll.max())} EUR "
           f"({pct(ll.mean() / a.total.mean(), 2)} du PnL moyen en valeur absolue).",
           f"- Jours de fixing (composante non nulle) : {int((a.fixings > 0.5).sum())}.",
           f"- Saut de base IRS 10Y (+{str(SAUT['bp']).replace('.', ',')} bp à partir du {SAUT['debut']}, "
           f"{SAUT['jours']} jours) : |résiduel| max {eur(saut.residuel.abs().max())} EUR ces jours-là. Un mouvement "
           "isolé d'une cotation déplace la courbe Hagan-West hors de sa région, d'où le pire jour de l'année.",
           f"- Temps de calcul : {duree:.0f} s pour {len(df)} jours ({str(round(duree / len(df), 1)).replace('.', ',')} s par jour, Hagan-West, "
           "cinq constructions de courbes par jour).", "",
           "Série complète : [`pnl_serie.csv`](pnl_serie.csv)."]
    Path(__file__).with_suffix(".md").write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    print(Path(__file__).with_suffix(".md"))


if __name__ == "__main__":
    main()
