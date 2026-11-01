"""Reconstitution de cotations quotidiennes EUR à partir des séries BCE, et lecture d'un fichier de cotations.

Il n'existe pas de source gratuite de cotations de swaps : les niveaux sont reconstitués (hypotheses.md).
Format du fichier (une ligne par cotation, taux en %) : date,type,tenor,taux,source
  type   : ESTR (tenor ON), OIS, DEPOT, FRA (tenor "1x7"), IRS (contre EURIBOR 6M)
  source : "reconstitue" ou "reel" — de vraies cotations se chargent avec le même format.

`python -m courbes.cotations` régénère data/cotations.csv et affiche les chiffres repris dans hypotheses.md.
"""
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from courbes import dates as dt
from courbes.donnees import DEBUT, FIN, serie

FICHIER = Path(__file__).resolve().parent.parent / "data" / "cotations.csv"
COLONNES = ["date", "type", "tenor", "taux", "source"]
SOURCES = {"reconstitue", "reel"}

OIS_TENORS = ["1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y", "18M", "2Y", "3Y", "4Y", "5Y", "6Y", "7Y",
              "8Y", "9Y", "10Y", "12Y", "15Y", "20Y", "25Y", "30Y"]
FRA_DEBUTS = [1, 2, 3, 6, 9, 12, 18]  # FRA 1x7 ... 18x24
IRS_TENORS = ["2Y", "3Y", "4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y", "12Y", "15Y", "20Y", "25Y", "30Y"]
BRUIT_BP = {"OIS": 0.2, "IRS": 0.3, "FRA": 0.4, "DEPOT": 0.5}  # écart-type du bruit gaussien
TAU_DECALAGE = 1.0  # années : vitesse à laquelle l'écart €STR - AAA s'éteint le long de la courbe
SAUT = {"type": "IRS", "tenor": "10Y", "debut": date(2026, 5, 4), "jours": 5, "bp": 2.5}
GRAINE = 20261101


def svensson(t: float, b0, b1, b2, b3, t1, t2) -> float:
    """Taux zéro BCE (Svensson, composition continue, %) à t années."""
    if t < 1e-8:
        return b0 + b1
    x1, x2 = t / t1, t / t2
    f1 = (1 - math.exp(-x1)) / x1
    return b0 + b1 * f1 + b2 * (f1 - math.exp(-x1)) + b3 * ((1 - math.exp(-x2)) / x2 - math.exp(-x2))


def decalage(t: float, params, estr: float) -> float:
    """Écart (%) ajouté au zéro AAA : €STR - zéro AAA instantané, éteint exponentiellement."""
    r0 = math.log1p(estr / 36000) * 36500  # €STR (ACT/360, 1 jour) en composition continue
    return (r0 - (params[0] + params[1])) * math.exp(-t / TAU_DECALAGE)


def actualisation(jour: date, params, estr: float):
    """Facteurs d'actualisation €STR reconstitués pour la date de cotation `jour`."""
    def P(d: date) -> float:
        t = dt.year_fraction(jour, d, "ACT/365F")
        return math.exp(-(svensson(t, *params) + decalage(t, params, estr)) / 100 * t)
    return P


def forward(P, a: date, b: date) -> float:
    """Taux simple ACT/360 entre a et b (décimal)."""
    return (P(a) / P(b) - 1) / dt.year_fraction(a, b, "ACT/360")


def ois_par(P, spot: date, tenor: str) -> float:
    """Taux OIS €STR : un seul flux jusqu'à 1 an puis annuel, ACT/360, MF fin de mois, paiement J+1."""
    fin = dt.advance(spot, tenor, "MF", eom=True)
    n, u = dt.parse_tenor(tenor)
    mois = n * 12 if u == "Y" else n if u == "M" else 0
    echeances = dt.schedule(spot, fin, "1Y", "MF", eom=True) if mois > 12 else [spot, fin]
    flottant = fixe = 0.0
    for a, b in zip(echeances, echeances[1:]):
        p = P(dt.add_business_days(b, 1))
        flottant += (P(a) / P(b) - 1) * p
        fixe += dt.year_fraction(a, b, "ACT/360") * p
    return flottant / fixe


def irs_par(P, spot: date, tenor: str, base: float) -> float:
    """Taux de swap contre EURIBOR 6M : fixe annuel 30/360, variable semestriel ACT/360, MF, à rebours."""
    fin = dt.advance(spot, tenor, "MF")
    fixe = dt.schedule(spot, fin, "1Y", "MF")
    var = dt.schedule(spot, fin, "6M", "MF")
    # shortcut: forward EURIBOR sur la période de calcul (pas sur la période de fixing J-2), écart < 0.1 bp
    num = sum((forward(P, a, b) + base) * dt.year_fraction(a, b, "ACT/360") * P(b) for a, b in zip(var, var[1:]))
    den = sum(dt.year_fraction(a, b, "30/360") * P(b) for a, b in zip(fixe, fixe[1:]))
    return num / den


def _marche() -> pd.DataFrame:
    """Paramètres Svensson et €STR sur les jours communs aux deux séries."""
    noms = ["beta0", "beta1", "beta2", "beta3", "tau1", "tau2", "estr"]
    return pd.DataFrame({n: serie(n) for n in noms}).dropna()


def bases_mensuelles(marche: pd.DataFrame) -> dict:
    """Base EURIBOR 6M - OIS par mois : moyenne mensuelle BCE moins moyenne du forward OIS 6M reconstitué."""
    euribor = serie("euribor6m")
    modele: dict[str, list] = {}
    for jour, r in marche.iterrows():
        P = actualisation(jour, r.iloc[:6].tolist(), r.estr)
        spot = dt.add_business_days(jour, 2)
        modele.setdefault(f"{jour:%Y-%m}", []).append(forward(P, spot, dt.advance(spot, "6M", "MF")))
    bases, derniere = {}, None
    for mois, f in modele.items():
        if mois in euribor.index:
            derniere = euribor[mois] / 100 - float(np.mean(f))
        bases[mois] = derniere  # mois pas encore publié : base du dernier mois connu
    return bases


def reconstituer(debut: date = DEBUT, fin: date = FIN, graine: int = GRAINE, bruit: bool = True) -> pd.DataFrame:
    marche = _marche()
    bases = bases_mensuelles(marche)
    rng = np.random.default_rng(graine)
    jours_saut = [j for j in marche.index if j >= SAUT["debut"]][: SAUT["jours"]]
    lignes = []
    for jour, r in marche.loc[debut:fin].iterrows():
        P = actualisation(jour, r.iloc[:6].tolist(), r.estr)
        spot = dt.add_business_days(jour, 2)
        base = bases[f"{jour:%Y-%m}"]
        cot = [("OIS", t, ois_par(P, spot, t)) for t in OIS_TENORS]
        cot.append(("DEPOT", "6M", forward(P, spot, dt.advance(spot, "6M", "MF")) + base))
        for m in FRA_DEBUTS:
            a = dt.advance(spot, f"{m}M", "MF")
            cot.append(("FRA", f"{m}x{m + 6}", forward(P, a, dt.advance(a, "6M", "MF")) + base))
        cot += [("IRS", t, irs_par(P, spot, t, base)) for t in IRS_TENORS]

        lignes.append((jour, "ESTR", "ON", r.estr))  # fixing publié, non bruité
        for typ, tenor, taux in cot:
            taux *= 100
            if bruit:
                taux += rng.normal(0, BRUIT_BP[typ]) / 100
                if (typ, tenor) == (SAUT["type"], SAUT["tenor"]) and jour in jours_saut:
                    taux += SAUT["bp"] / 100
            lignes.append((jour, typ, tenor, taux))
    df = pd.DataFrame(lignes, columns=COLONNES[:4])
    df["taux"] = df.taux.round(5)
    df["source"] = "reconstitue"
    return df


def _tenor_valide(typ: str, tenor: str) -> bool:
    if typ == "ESTR":
        return tenor == "ON"
    try:
        if typ == "FRA":
            a, b = (int(x) for x in tenor.split("x"))
            return 0 <= a < b
        return dt.parse_tenor(tenor)[0] > 0
    except ValueError:
        return False


def lire_cotations(path=FICHIER) -> pd.DataFrame:
    """Charge et valide un fichier de cotations (reconstituées ou réelles)."""
    df = pd.read_csv(path, dtype={"tenor": str, "type": str, "source": str})
    if list(df.columns) != COLONNES:
        raise ValueError(f"colonnes attendues {COLONNES}, trouvées {list(df.columns)}")
    df["date"] = pd.to_datetime(df.date, format="%Y-%m-%d").dt.date
    df["taux"] = pd.to_numeric(df.taux, errors="raise")
    erreurs = []
    if not df.taux.map(math.isfinite).all():
        erreurs.append("taux non finis")
    if bad := set(df.source) - SOURCES:
        erreurs.append(f"sources inconnues {bad}")
    if bad := {(t, n) for t, n in zip(df.type, df.tenor) if t not in BRUIT_BP and t != "ESTR" or not _tenor_valide(t, n)}:
        erreurs.append(f"type/ténor invalides {sorted(bad)[:5]}")
    if df.duplicated(["date", "type", "tenor"]).any():
        erreurs.append("cotations en double")
    if erreurs:
        raise ValueError("; ".join(erreurs))
    return df


if __name__ == "__main__":
    df = reconstituer()
    FICHIER.parent.mkdir(exist_ok=True)
    df.to_csv(FICHIER, index=False, date_format="%Y-%m-%d")
    print(f"{len(df)} cotations, {df.date.nunique()} jours, {df.date.min()} -> {df.date.max()}")

    marche = _marche().loc[DEBUT:FIN]
    for t in (0.25, 1, 2, 5, 10):
        d = [decalage(t, r.iloc[:6].tolist(), r.estr) * 100 for _, r in marche.iterrows()]
        print(f"décalage €STR-AAA à {t:>5} an(s) : moyenne {np.mean(d):+.1f} bp, min {min(d):+.1f}, max {max(d):+.1f}")
    b = [v * 1e4 for m, v in bases_mensuelles(_marche()).items()]
    print(f"base EURIBOR 6M - OIS mensuelle : min {min(b):.1f} bp, max {max(b):.1f} bp")
