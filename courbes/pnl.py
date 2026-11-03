"""PnL explain d'un portefeuille de swaps entre deux jours de cotation t0 et t1.

PnL = V1 + flux payés − V0 = portage + fixings + Σ_k bucket_k Δq_k + ½ Γ Δq̄² + résiduel :
- portage : marché qui réalise les forwards de t0. Courbes de t0 portées en t1, P(d) / P(t1), traduites en cotations
  (q_c) puis rebootstrapées en t1 ; fixings tombés dans [t0, t1[ pris aux forwards ;
- fixings : écart des fixings publiés à ces forwards (fixings reconstitués : composante construite par hypothèse) ;
- delta : buckets des courbes portées × (q1 − q_c), en bp ; gamma : gamma parallèle des courbes portées × Δq̄²,
  Δq̄ = moyenne des Δq ; résiduel : le reste (gamma croisé, ordre 3).
"""
import numpy as np

from courbes import dates as dt
from courbes import risque as r
from courbes.curves import CourbeHW, instrument_6m
from courbes.instruments import OIS


def cotations_portees(estr, six, ois: dict, six_q: dict, jour1):
    """Cotations (en %) que donneraient en t1 les courbes de t0 si les forwards se réalisaient."""
    pd1, p61 = estr.P(jour1), six.P(jour1)
    Pd, P6 = (lambda d: estr.P(d) / pd1), (lambda d: six.P(d) / p61)
    spot = dt.add_business_days(jour1, 2)
    return ({t: OIS(spot, t).taux(Pd) * 100 for t in ois},
            {k: instrument_6m(spot, k).taux(P6, Pd) * 100 for k in six_q})


def _cles(estr, six):
    return [i.tenor for i in estr.instruments] + [r.cle(i) for i in six.instruments]


def expliquer(swaps, jour0, jour1, cot0, cot1, fixing, classe=CourbeHW, h_bp: float = 1.0) -> dict:
    """cot0, cot1 : (cotations OIS, cotations 6M) en %, au format de `risque.construire`. Montants en EUR."""
    e0, k0 = r.construire(jour0, *cot0, classe)
    v0 = r.valeur(swaps, jour0, e0, k0, fixing)
    qc = cotations_portees(e0, k0, *cot0, jour1)
    ec, kc = r.construire(jour1, *qc, classe)
    flux = sum(s.flux(jour0, jour1, fixing) for s in swaps)
    vp = sum(s.valeur(jour1, kc.P, ec.P, fixing, coupure=jour0) for s in swaps)
    vc, b = r.buckets(swaps, jour1, ec, kc, fixing)

    bump = lambda d: r.valeur(swaps, jour1, *r.construire(  # noqa: E731
        jour1, *({k: v + d / 100 for k, v in q.items()} for q in qc), classe), fixing)
    gamma = (bump(h_bp) - 2 * vc + bump(-h_bp)) / h_bp ** 2  # EUR / bp²

    q1, q0 = {**cot1[0], **cot1[1]}, {**qc[0], **qc[1]}
    dq = np.array([(q1[k] - q0[k]) * 100 for k in _cles(ec, kc)])  # bp
    e1, k1 = r.construire(jour1, *cot1, classe)
    v1 = r.valeur(swaps, jour1, e1, k1, fixing)

    res = {"total": v1 + flux - v0, "portage": vp + flux - v0, "fixings": vc - vp, "delta": float(b @ dq),
           "gamma": 0.5 * gamma * dq.mean() ** 2}
    res["residuel"] = res["total"] - sum(v for k, v in res.items() if k != "total")
    return res
