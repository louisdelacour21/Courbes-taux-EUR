"""Rapport de validation : recalcule chaque seuil chiffré, assemble les études et produit rapport/rapport_validation.pdf.

    python etudes/rapport.py    (quelques minutes ; Edge pour la conversion PDF)
"""
import base64
import html
import io
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "tests"))
from courbes import cotations as c  # noqa: E402
from courbes import synthese as sy  # noqa: E402
from courbes.curves import Courbe, CourbeHW  # noqa: E402
from courbes.risque import construire  # noqa: E402
from ql_banc import courbe_estr as estr_ql, courbe_euribor6m as e6m_ql, jours_du_banc, q  # noqa: E402

ETUDES = RACINE / "etudes"
SORTIE = RACINE / "rapport"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
TOL_REPRICING, TOL_QL = 1e-13, 1e-10
INTERP = {"Log-linéaire": Courbe, "Hagan-West": CourbeHW}


def banc_quantlib(cot):
    """Écarts max (repricing, DF €STR, DF 6M contre QuantLib) sur les jours du banc, par interpolation."""
    res = {}
    jours = jours_du_banc(cot)
    for nom, classe in INTERP.items():
        hw = classe is CourbeHW
        rep = df_estr = df_6m = 0.0
        for jour in jours:
            ois, six = c.du_jour(cot, jour)
            estr, k6 = construire(jour, ois, six, classe)
            kestr, _ = estr_ql(jour, ois, hw=hw)
            k6ql, _ = e6m_ql(jour, k6.instruments, [v * 100 for v in k6.cotations], kestr, hw=hw)
            rep = max(rep, *(abs(i.taux(estr.P) - v) for i, v in zip(estr.instruments, estr.cotations)),
                      *(abs(i.taux(k6.P, estr.P) - v) for i, v in zip(k6.instruments, k6.cotations)))
            dates = [jour + timedelta(days=d) for d in range(1, 40 * 365, 29)]
            df_estr = max(df_estr, *(abs(estr.P(d) - kestr.discount(q(d))) for d in dates))
            df_6m = max(df_6m, *(abs(k6.P(d) - k6ql.discount(q(d))) for d in dates))
        res[nom] = (len(jours), rep, df_estr, df_6m)
    return res


def figure(trace) -> str:
    fig, ax = plt.subplots(figsize=(7.5, 3))
    trace(ax)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def md_html(md: str) -> str:
    """Le sous-ensemble de Markdown des études : titres, tableaux, puces, gras, code, liens."""
    def ligne(t):
        t = html.escape(t, quote=False)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"\[`?([^\]`]+)`?\]\([^)]+\)", r"<code>\1</code>", t)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)

    out, table, liste = [], [], False
    for s in [x.strip() for x in md.splitlines()] + [""]:
        if s.startswith("|"):
            table.append([ligne(x.strip()) for x in s.strip("|").split("|")])
            continue
        if table:
            corps = [r for r in table[1:] if not set("".join(r)) <= set("-: ")]
            out.append("<table><tr>" + "".join(f"<th>{x}</th>" for x in table[0]) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in corps) + "</table>")
            table = []
        if s.startswith("- ") != liste:
            out.append("</ul>" if liste else "<ul>")
            liste = not liste
        if s.startswith("#"):
            n = len(s) - len(s.lstrip("#"))
            out.append(f"<h{n + 2}>{ligne(s[n:].strip())}</h{n + 2}>")
        elif s.startswith("- "):
            out.append(f"<li>{ligne(s[2:])}</li>")
        elif s:
            out.append(f"<p>{ligne(s)}</p>")
    return "\n".join(out)


def ok(x, seuil) -> str:
    return f'{x:.1e} <span class="{"ok" if x < seuil else "ko"}">{"OK" if x < seuil else "KO"}</span>'


def main():
    cot = c.lire_cotations()
    jour = max(cot.date.unique())
    t0 = time.perf_counter()
    banc = banc_quantlib(cot)
    t_banc = time.perf_counter() - t0
    s = sy.synthese(jour)
    serie = pd.read_csv(ETUDES / "pnl_serie.csv", parse_dates=["jour"])
    part = serie.residuel.abs().mean() / serie.total.abs().mean()
    part_ll = serie.residuel_loglin.abs().mean() / serie.total.abs().mean()
    seuil = (sy.SEUIL_RESIDUEL * serie.total.abs()).clip(lower=sy.SEUIL_RESIDUEL_EUR)
    n_alertes = int((serie.residuel.abs() > seuil).sum())
    reconstitution = subprocess.run(["git", "log", "-1", "--format=%ad", "--date=format:%d/%m/%Y", "--",
                                     "data/cotations.csv"], cwd=RACINE, capture_output=True, text=True).stdout.strip()

    ois, six = c.du_jour(cot, jour)
    k6 = {n: construire(jour, ois, six, cl)[1] for n, cl in INTERP.items()}
    debuts = [jour + timedelta(days=2 + 30 * m) for m in range(29 * 12)]

    def fwd(ax):
        for n, k in k6.items():
            ax.plot([(d - jour).days / 365 for d in debuts],
                    [(k.P(d) / k.P(d + timedelta(days=182)) - 1) * 360 / 182 * 100 for d in debuts], label=n)
        ax.set(xlabel="années", ylabel="forward 6M (%)", title=f"Forwards EURIBOR 6M au {jour}")
        ax.legend()

    def res(ax):
        ax.plot(serie.jour, serie.residuel, label="Hagan-West", lw=1)
        ax.plot(serie.jour, serie.residuel_loglin, label="Log-linéaire (témoin)", lw=1)
        ax.set(ylabel="EUR", title="Résiduel quotidien du PnL explain")
        ax.legend()

    lignes_banc = "".join(f"<tr><td>{n}</td><td>{j}</td><td>{ok(r, TOL_REPRICING)}</td><td>{ok(a, TOL_QL)}</td>"
                          f"<td>{ok(b, TOL_QL)}</td></tr>" for n, (j, r, a, b) in banc.items())
    etudes = "".join(f'<section class="etude">{md_html((ETUDES / f).read_text(encoding="utf-8"))}</section>'
                     for f in ["leave_one_out.md", "nss.md", "risque.md", "pnl.md"])
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Rapport de validation</title><style>
body{{font:10.5pt/1.45 "Segoe UI",sans-serif;color:#1a1a1a;max-width:46em;margin:2em auto;padding:0 1em}}
h1{{font-size:19pt;margin-bottom:.2em}} h2{{font-size:14pt;border-bottom:1px solid #ccc;margin-top:1.6em}}
h3{{font-size:12pt}} h4{{font-size:11pt}} .bandeau{{background:#fff4d6;border-left:4px solid #d9a400;padding:.6em .9em}}
table{{border-collapse:collapse;margin:.6em 0;font-size:9.5pt}} td,th{{border:1px solid #ccc;padding:2px 6px}}
th{{background:#f2f2f2}} td:not(:first-child){{text-align:right}} img{{width:100%}} code{{font-size:9pt}}
.ok{{color:#11713a;font-weight:600}} .ko{{color:#b00020;font-weight:600}} pre{{background:#f6f6f6;padding:.6em;font-size:9pt;white-space:pre-wrap}}
h3{{break-after:avoid}} table{{break-inside:auto}}</style></head><body>
<h1>Courbes de taux EUR multi-courbes et pricer de swaps</h1>
<p>Rapport de validation, généré le {date.today():%d/%m/%Y} par <code>etudes/rapport.py</code>.</p>
<div class="bandeau">Niveaux reconstitués le {reconstitution} depuis les données publiques BCE ; validation QuantLib
indépendante de la provenance ; études d'interpolation et PnL explain sur données synthétiques.</div>
<p><b>Auto-revue</b> par l'auteur du modèle, et non une validation indépendante au sens de SR 11-7 : pas de séparation
des fonctions, pas de revue du cadre d'utilisation. Chaque seuil chiffré ci-dessous est recalculé par ce script.</p>

<h2>1. Seuils recalculés</h2>
<h3>Repricing et banc QuantLib</h3>
<p>Jours du banc : un sur dix, fins de mois et dernier jour. Écarts maximaux sur les instruments de calage (repricing,
seuil {TOL_REPRICING:.0e}) et sur les facteurs d'actualisation, tous les 29 jours jusqu'à 40 ans, contre QuantLib
(seuil {TOL_QL:.0e}). Durée : {t_banc:.0f} s.</p>
<table><tr><th>Interpolation</th><th>Jours</th><th>Repricing max</th><th>DF €STR max</th><th>DF 6M max</th></tr>
{lignes_banc}</table>
<h3>PnL explain</h3>
<p>{len(serie)} jours : résiduel moyen en valeur absolue = {part:.2%} du PnL moyen en valeur absolue (Hagan-West),
{part_ll:.2%} pour le témoin log-linéaire. Seuil d'alerte de la synthèse du matin : |résiduel| &gt;
max({sy.SEUIL_RESIDUEL:.0%} du PnL, {sy.eur(sy.SEUIL_RESIDUEL_EUR)} EUR) ; jours au-dessus : {n_alertes}.</p>
{figure(res)}

<h2>2. Interpolation</h2>
{figure(fwd)}
<p>Log-linéaire sur ln P : forwards en escalier. Hagan-West (monotone convexe) : forwards continus, retenu par le
test leave-one-out (section 4). Contrepartie : la valeur n'est pas dérivable en les cotations, d'où le résiduel du
PnL explain.</p>

<h2>3. Synthèse du matin</h2>
<pre>{html.escape(sy.texte(s))}</pre>

<h2>4. Études</h2>
<p>Résultats produits par <code>etudes/leave_one_out.py</code>, <code>nss.py</code>, <code>risque.py</code> et
<code>pnl.py</code>, repris tels quels.</p>
{etudes}

<h2>Limites</h2>
<ul><li>Cotations reconstituées (courbes AAA BCE, €STR, bases mensuelles), pas de cotations de marché réelles.</li>
<li>Fixings EURIBOR 6M passés reconstitués par la cotation DEPOT 6M du jour.</li>
<li>Pas d'ajustement de convexité, de CSA autre que cash EUR, ni de courbe 3M.</li></ul>
</body></html>"""
    SORTIE.mkdir(exist_ok=True)
    fichier = SORTIE / "rapport_validation.html"
    fichier.write_bytes(page.encode("utf-8"))
    pdf = SORTIE / "rapport_validation.pdf"
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profil:  # profil à part : sinon Edge confie le travail à l'instance ouverte
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profil}",
                        "--no-pdf-header-footer", f"--print-to-pdf={pdf}", fichier.as_uri()], timeout=120)
        for _ in range(60):  # le lanceur d'Edge rend la main avant que le PDF soit écrit
            if pdf.exists():
                break
            time.sleep(1)
    print(pdf, "OK" if pdf.exists() else "ÉCHEC")
    for n, (j, r, a, b) in banc.items():
        print(f"{n} : {j} jours, repricing {r:.1e}, DF €STR {a:.1e}, DF 6M {b:.1e}")
    print(f"PnL explain : {part:.2%} (témoin {part_ll:.2%}), {n_alertes} jours d'alerte")


if __name__ == "__main__":
    main()
