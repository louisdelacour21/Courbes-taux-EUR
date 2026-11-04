"""Validation report: recomputes every numerical threshold, assembles the studies and writes report/validation_report.pdf.

    python studies/report.py    (a few minutes; Edge for the PDF conversion)
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from ratecurves import briefing as br  # noqa: E402
from ratecurves import quotes as c  # noqa: E402
from ratecurves.curves import Curve, CurveHW  # noqa: E402
from ratecurves.risk import build  # noqa: E402
from ql_bench import bench_days, estr_curve as estr_ql, euribor6m_curve as e6m_ql, q  # noqa: E402

STUDIES = ROOT / "studies"
OUT = ROOT / "report"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
TOL_REPRICING, TOL_QL = 1e-13, 1e-10
INTERP = {"Log-linear": Curve, "Hagan-West": CurveHW}


def quantlib_bench(quotes):
    """Max gaps (repricing, €STR DF, 6M DF against QuantLib) over the bench days, per interpolation."""
    res = {}
    days = bench_days(quotes)
    for name, cls in INTERP.items():
        hw = cls is CurveHW
        rep = df_estr = df_6m = 0.0
        for day in days:
            ois, six = c.of_day(quotes, day)
            estr, k6 = build(day, ois, six, cls)
            kestr, _ = estr_ql(day, ois, hw=hw)
            k6ql, _ = e6m_ql(day, k6.instruments, [v * 100 for v in k6.quotes], kestr, hw=hw)
            rep = max(rep, *(abs(i.rate(estr.P) - v) for i, v in zip(estr.instruments, estr.quotes)),
                      *(abs(i.rate(k6.P, estr.P) - v) for i, v in zip(k6.instruments, k6.quotes)))
            dates = [day + timedelta(days=d) for d in range(1, 40 * 365, 29)]
            df_estr = max(df_estr, *(abs(estr.P(d) - kestr.discount(q(d))) for d in dates))
            df_6m = max(df_6m, *(abs(k6.P(d) - k6ql.discount(q(d))) for d in dates))
        res[name] = (len(days), rep, df_estr, df_6m)
    return res


def figure(plot) -> str:
    fig, ax = plt.subplots(figsize=(7.5, 3))
    plot(ax)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def md_html(md: str) -> str:
    """The Markdown subset of the studies: headings, tables, bullets, bold, code, links."""
    def line(t):
        t = html.escape(t, quote=False)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"\[`?([^\]`]+)`?\]\([^)]+\)", r"<code>\1</code>", t)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)

    out, table, bullets = [], [], False
    for s in [x.strip() for x in md.splitlines()] + [""]:
        if s.startswith("|"):
            table.append([line(x.strip()) for x in s.strip("|").split("|")])
            continue
        if table:
            body = [r for r in table[1:] if not set("".join(r)) <= set("-: ")]
            out.append("<table><tr>" + "".join(f"<th>{x}</th>" for x in table[0]) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in body) + "</table>")
            table = []
        if s.startswith("- ") != bullets:
            out.append("</ul>" if bullets else "<ul>")
            bullets = not bullets
        if s.startswith("#"):
            n = len(s) - len(s.lstrip("#"))
            out.append(f"<h{n + 2}>{line(s[n:].strip())}</h{n + 2}>")
        elif s.startswith("- "):
            out.append(f"<li>{line(s[2:])}</li>")
        elif s:
            out.append(f"<p>{line(s)}</p>")
    return "\n".join(out)


def ok(x, threshold) -> str:
    return f'{x:.1e} <span class="{"ok" if x < threshold else "ko"}">{"OK" if x < threshold else "FAIL"}</span>'


def main():
    quotes = c.read_quotes()
    day = max(quotes.date.unique())
    t0 = time.perf_counter()
    bench = quantlib_bench(quotes)
    t_bench = time.perf_counter() - t0
    s = br.briefing(day)
    series = pd.read_csv(STUDIES / "pnl_series.csv", parse_dates=["day"])
    share = series.residual.abs().mean() / series.total.abs().mean()
    share_ll = series.residual_loglin.abs().mean() / series.total.abs().mean()
    threshold = (br.RESIDUAL_THRESHOLD * series.total.abs()).clip(lower=br.RESIDUAL_THRESHOLD_EUR)
    n_alerts = int((series.residual.abs() > threshold).sum())
    rebuilt = subprocess.run(["git", "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d", "--",
                              "data/quotes.csv"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    ois, six = c.of_day(quotes, day)
    k6 = {n: build(day, ois, six, cl)[1] for n, cl in INTERP.items()}
    starts = [day + timedelta(days=2 + 30 * m) for m in range(29 * 12)]

    def fwd(ax):
        for n, k in k6.items():
            ax.plot([(d - day).days / 365 for d in starts],
                    [(k.P(d) / k.P(d + timedelta(days=182)) - 1) * 360 / 182 * 100 for d in starts], label=n)
        ax.set(xlabel="years", ylabel="6M forward (%)", title=f"EURIBOR 6M forwards on {day}")
        ax.legend()

    def res(ax):
        ax.plot(series.day, series.residual, label="Hagan-West", lw=1)
        ax.plot(series.day, series.residual_loglin, label="Log-linear (twin)", lw=1)
        ax.set(ylabel="EUR", title="Daily PnL explain residual")
        ax.legend()

    bench_rows = "".join(f"<tr><td>{n}</td><td>{j}</td><td>{ok(r, TOL_REPRICING)}</td><td>{ok(a, TOL_QL)}</td>"
                         f"<td>{ok(b, TOL_QL)}</td></tr>" for n, (j, r, a, b) in bench.items())
    studies = "".join(f'<section class="study">{md_html((STUDIES / f).read_text(encoding="utf-8"))}</section>'
                      for f in ["leave_one_out.md", "nss.md", "risk.md", "pnl.md"])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Validation report</title><style>
body{{font:10.5pt/1.45 "Segoe UI",sans-serif;color:#1a1a1a;max-width:46em;margin:2em auto;padding:0 1em}}
h1{{font-size:19pt;margin-bottom:.2em}} h2{{font-size:14pt;border-bottom:1px solid #ccc;margin-top:1.6em}}
h3{{font-size:12pt}} h4{{font-size:11pt}} .banner{{background:#fff4d6;border-left:4px solid #d9a400;padding:.6em .9em}}
table{{border-collapse:collapse;margin:.6em 0;font-size:9.5pt}} td,th{{border:1px solid #ccc;padding:2px 6px}}
th{{background:#f2f2f2}} td:not(:first-child){{text-align:right}} img{{width:100%}} code{{font-size:9pt}}
.ok{{color:#11713a;font-weight:600}} .ko{{color:#b00020;font-weight:600}} pre{{background:#f6f6f6;padding:.6em;font-size:9pt;white-space:pre-wrap}}
h3{{break-after:avoid}} table{{break-inside:auto}}</style></head><body>
<h1>Multi-curve EUR rate curves and swap pricer</h1>
<p>Validation report, generated on {date.today():%Y-%m-%d} by <code>studies/report.py</code>.</p>
<div class="banner">Levels reconstructed on {rebuilt} from public ECB data; QuantLib validation independent of the
data source; interpolation and PnL explain studies on synthetic data.</div>
<p><b>Self-review</b> by the model author, not an independent validation in the SR 11-7 sense: no separation of
functions, no review of the usage framework. Every numerical threshold below is recomputed by this script.</p>

<h2>1. Recomputed thresholds</h2>
<h3>Repricing and QuantLib bench</h3>
<p>Bench days: one in ten, month ends and the last day. Maximum gaps on the calibration instruments (repricing,
threshold {TOL_REPRICING:.0e}) and on the discount factors, every 29 days up to 40 years, against QuantLib
(threshold {TOL_QL:.0e}). Run time: {t_bench:.0f} s.</p>
<table><tr><th>Interpolation</th><th>Days</th><th>Max repricing</th><th>Max €STR DF</th><th>Max 6M DF</th></tr>
{bench_rows}</table>
<h3>PnL explain</h3>
<p>{len(series)} days: mean absolute residual = {share:.2%} of the mean absolute PnL (Hagan-West),
{share_ll:.2%} for the log-linear twin. Morning briefing alert threshold: |residual| &gt;
max({br.RESIDUAL_THRESHOLD:.0%} of PnL, {br.eur(br.RESIDUAL_THRESHOLD_EUR)} EUR); days above: {n_alerts}.</p>
{figure(res)}

<h2>2. Interpolation</h2>
{figure(fwd)}
<p>Log-linear on ln P: step-like forwards. Hagan-West (monotone convex): continuous forwards, chosen by the
leave-one-out test (section 4). The trade-off: the value is not differentiable in the quotes, hence the PnL explain
residual.</p>

<h2>3. Morning briefing</h2>
<pre>{html.escape(br.text(s))}</pre>

<h2>4. Studies</h2>
<p>Results produced by <code>studies/leave_one_out.py</code>, <code>nss.py</code>, <code>risk.py</code> and
<code>pnl.py</code>, included as is.</p>
{studies}

<h2>Limitations</h2>
<ul><li>Reconstructed quotes (ECB AAA curves, €STR, monthly bases), not real market quotes.</li>
<li>Past EURIBOR 6M fixings reconstructed from the DEPOSIT 6M quote of the day.</li>
<li>No convexity adjustment, no CSA other than EUR cash, no 3M curve.</li></ul>
</body></html>"""
    OUT.mkdir(exist_ok=True)
    out = OUT / "validation_report.html"
    out.write_bytes(page.encode("utf-8"))
    pdf = OUT / "validation_report.pdf"
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:  # separate profile, or Edge hands the job to the open instance
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                        "--no-pdf-header-footer", f"--print-to-pdf={pdf}", out.as_uri()], timeout=120)
        for _ in range(60):  # the Edge launcher returns before the PDF is written
            if pdf.exists():
                break
            time.sleep(1)
    print(pdf, "OK" if pdf.exists() else "FAILED")
    for n, (j, r, a, b) in bench.items():
        print(f"{n}: {j} days, repricing {r:.1e}, €STR DF {a:.1e}, 6M DF {b:.1e}")
    print(f"PnL explain: {share:.2%} (twin {share_ll:.2%}), {n_alerts} alert days")


if __name__ == "__main__":
    main()
