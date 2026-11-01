"""NSS ajusté chaque jour aux zéros bootstrapés (Hagan-West) : RMSE, stabilité des paramètres, extrapolation.

Le RMSE n'a de sens que sur les cotations bruitées : sans bruit, les cotations dérivent d'une courbe Svensson et
l'ajustement est quasi parfait par construction (contrôle fait un jour sur dix).

    python etudes/nss.py   →   etudes/nss.md, etudes/nss_parametres.csv
"""
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from courbes import cotations as c  # noqa: E402
from courbes import dates as dt  # noqa: E402
from courbes.curves import CourbeHW, courbe_estr, courbe_euribor6m  # noqa: E402
from courbes.nss import ajuster_courbe  # noqa: E402


def courbes_du_jour(g, jour):
    o = g[g.type == "OIS"]
    estr = courbe_estr(jour, dict(zip(o.tenor, o.taux)), CourbeHW)
    six = {f"{r.type} {r.tenor}": r.taux for r in g[g.type.isin(["DEPOT", "FRA", "IRS"])].itertuples()}
    return {"€STR": estr, "6M": courbe_euribor6m(jour, six, estr, CourbeHW)}


def main():
    bruitees = c.lire_cotations()
    jours = sorted(bruitees.date.unique())
    controle = set(jours[::10])
    propres = c.reconstituer(bruit=False)
    lignes = []
    for jour in jours:
        for source, cot in (("bruité", bruitees), ("sans bruit", propres)):
            if source == "sans bruit" and jour not in controle:
                continue
            for nom, k in courbes_du_jour(cot[cot.date == jour], jour).items():
                m = ajuster_courbe(k)
                t = k.t[1:]
                res = (m.zero(t) + k.x / t) * 1e4
                d40 = jour + timedelta(days=round(40 * 365.25))
                t40 = dt.year_fraction(jour, d40, "ACT/365F")
                d10 = dt.add_months(jour, 120)
                t10 = dt.year_fraction(jour, d10, "ACT/365F")
                lignes.append(dict(date=jour, source=source, courbe=nom, rmse_bp=m.rmse * 1e4,
                                   max_bp=np.abs(res).max(), z10=-k.ln_p(d10) / t10, b0=m.beta[0], b1=m.beta[1], b2=m.beta[2],
                                   b3=m.beta[3], l1=m.l1, l2=m.l2,
                                   extrapolation_40y_bp=(m.zero([t40])[0] + k.ln_p(d40) / t40) * 1e4))
        print(jour, flush=True)
    df = pd.DataFrame(lignes)
    df[df.source == "bruité"].drop(columns="source").to_csv(Path(__file__).with_name("nss_parametres.csv"),
                                                              index=False, float_format="%.8g")

    md = ["# NSS ajusté aux zéros bootstrapés (Hagan-West)", "",
          f"{len(jours)} jours de cotations bruitées ; contrôle sans bruit un jour sur dix ({len(controle)} jours). "
          "Ajustement aux zéros des piliers, poids égaux.", "",
          "| Courbe | Cotations | RMSE moyen (bp) | RMSE max (bp) | Résidu max (bp) |", "|---|---|---|---|---|"]
    for (nom, src), g in df.groupby(["courbe", "source"], sort=False):
        md.append(f"| {nom} | {src} | {g.rmse_bp.mean():.2f} | {g.rmse_bp.max():.2f} | {g.max_bp.max():.2f} |")

    md += ["", "Stabilité jour à jour (cotations bruitées) : écart-type des variations quotidiennes, en bp, "
           "et nombre de jours où un λ varie de plus de 50 %.", "",
           "| Courbe | Δ zéro 10Y | Δ β0 (niveau) | Δ β1 (−pente) | Δ β2 (courbure) | Δ β3 | sauts de λ |",
           "|---|---|---|---|---|---|---|"]
    for nom, g in df[df.source == "bruité"].groupby("courbe", sort=False):
        g = g.sort_values("date")
        sd = lambda s: f"{s.diff().std() * 1e4:.1f}"
        sauts = int(((g.l1.pct_change().abs() > 0.5) | (g.l2.pct_change().abs() > 0.5)).sum())
        md.append(f"| {nom} | {sd(g.z10)} | {sd(g.b0)} | {sd(g.b1)} | {sd(g.b2)} | {sd(g.b3)} | {sauts} |")

    e = df[df.source == "bruité"].groupby("courbe", sort=False).extrapolation_40y_bp
    md += ["", "Extrapolation à 40 ans, NSS moins forward plat prolongé (bp) : "
           + " ; ".join(f"{n} moyenne {s.mean():+.1f}, min {s.min():+.1f}, max {s.max():+.1f}" for n, s in e)]
    Path(__file__).with_suffix(".md").write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    print("\n".join(md))


if __name__ == "__main__":
    main()
