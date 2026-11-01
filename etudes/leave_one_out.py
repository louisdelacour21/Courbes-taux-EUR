"""Leave-one-out : log-linéaire contre Hagan-West, sur les cotations bruitées (avec le saut de base de l'IRS 10Y).

Pour chaque jour et chaque instrument intérieur (ni le premier ni le dernier pilier : ce serait de l'extrapolation),
on retire l'instrument, on reconstruit la courbe et on mesure l'écart entre son taux implicite et sa cotation, en bp.
La courbe 6M est reconstruite sur la courbe €STR complète du même interpolateur.
Rugosité : Σ (Δf)² / Δt sur les forwards continus 1M mensuels jusqu'à 30 ans (proxy de ∫f'² ; infini en
log-linéaire à la limite, puisque les forwards y sont en escalier).

    python etudes/leave_one_out.py   →   etudes/leave_one_out.md
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from courbes import cotations as c  # noqa: E402
from courbes import dates as dt  # noqa: E402
from courbes.curves import Courbe, CourbeHW, courbe_estr, courbe_euribor6m, newton  # noqa: E402

CLASSES = {"log-linéaire": Courbe, "Hagan-West": CourbeHW}


def jours_etudies(cot):
    jours = sorted(cot.date.unique())
    saut = [j for j in jours if j >= c.SAUT["debut"]][: c.SAUT["jours"]]
    return sorted(set(jours[::10]) | set(saut)), set(saut)


def erreurs_loo(jour, instruments, q, actualisation, classe):
    """{ténor: écart en bp} pour chaque instrument intérieur retiré."""
    out = {}
    for k in range(1, len(instruments) - 1):
        reste = instruments[:k] + instruments[k + 1:]
        courbe = newton(jour, reste, np.delete(q, k), actualisation, classe)
        i = instruments[k]
        taux = i.taux(courbe.P, actualisation) if actualisation else i.taux(courbe.P)
        out[i.tenor] = (taux - q[k]) * 1e4
    return out


def rugosite(courbe):
    spot = dt.add_business_days(courbe.jour, 2)
    d = [dt.add_months(spot, m) for m in range(361)]
    t = [dt.year_fraction(courbe.jour, x, "ACT/365F") for x in d]
    f = [(courbe.ln_p(a) - courbe.ln_p(b)) / (tb - ta) for a, b, ta, tb in zip(d, d[1:], t, t[1:])]
    tm = [(a + b) / 2 for a, b in zip(t, t[1:])]
    return sum((f2 - f1) ** 2 / (t2 - t1) for f1, f2, t1, t2 in zip(f, f[1:], tm, tm[1:])) * 1e4  # bp²/an


def main():
    cot = c.lire_cotations()
    jours, saut = jours_etudies(cot)
    lignes = []  # (jour, courbe, classe, ténor, bp)
    rug = {(n, k): [] for n in ("€STR", "6M") for k in CLASSES}
    for jour in jours:
        g = cot[cot.date == jour]
        o = g[g.type == "OIS"]
        ois = dict(zip(o.tenor, o.taux))
        six = {f"{r.type} {r.tenor}": r.taux for r in g[g.type.isin(["DEPOT", "FRA", "IRS"])].itertuples()}
        for nom, classe in CLASSES.items():
            estr = courbe_estr(jour, ois, classe)
            q = np.array([ois[i.tenor] / 100 for i in estr.instruments])
            for t, e in erreurs_loo(jour, estr.instruments, q, None, classe).items():
                lignes.append((jour, "€STR", nom, t, e))
            c6 = courbe_euribor6m(jour, six, estr, classe)
            for t, e in erreurs_loo(jour, c6.instruments, np.array(c6.cotations), estr.P, classe).items():
                lignes.append((jour, "6M", nom, t, e))
            rug[("€STR", nom)].append(rugosite(estr))
            rug[("6M", nom)].append(rugosite(c6))
        print(jour, flush=True)

    def stats(filtre):
        e = np.abs([l[4] for l in lignes if filtre(l)])
        return f"{e.mean():.2f} | {e.max():.2f}"

    md = ["# Leave-one-out : log-linéaire contre Hagan-West", "",
          f"{len(jours)} jours (un jour de cotation sur dix + les {len(saut)} jours du saut de base de l'IRS 10Y), "
          "cotations bruitées. Écart |taux implicite − cotation| de l'instrument retiré, en bp.", "",
          "| Courbe | Interpolation | Moyenne | Max | Saut : moyenne | Saut : max | Rugosité moyenne (bp²/an) |",
          "|---|---|---|---|---|---|---|"]
    for n in ("€STR", "6M"):
        for k in CLASSES:
            md.append(f"| {n} | {k} | {stats(lambda l: l[1] == n and l[2] == k)} | "
                      f"{stats(lambda l: l[1] == n and l[2] == k and l[0] in saut)} | {np.mean(rug[(n, k)]):.1f} |")
    md += ["", "Par instrument retiré (tous jours, moyenne | max) :", "",
           "| Courbe | Instrument | LL moyenne | LL max | HW moyenne | HW max |", "|---|---|---|---|---|---|"]
    for n in ("€STR", "6M"):
        tenors = list(dict.fromkeys(l[3] for l in lignes if l[1] == n))
        for t in tenors:
            md.append(f"| {n} | {t} | " + " | ".join(stats(lambda l: l[1] == n and l[2] == k and l[3] == t)
                                                    for k in CLASSES) + " |")
    out = Path(__file__).with_suffix(".md")
    out.write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
