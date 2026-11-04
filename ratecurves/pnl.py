"""PnL explain of a swap portfolio between two quote days t0 and t1.

PnL = V1 + cash flows paid − V0 = carry + fixings + Σ_k bucket_k Δq_k + ½ Γ Δq̄² + residual:
- carry: market that realises the t0 forwards. t0 curves carried to t1, P(d) / P(t1), translated into quotes
  (q_c) then re-bootstrapped at t1; fixings falling in [t0, t1[ taken at the forwards;
- fixings: gap between the published fixings and these forwards (reconstructed fixings: assumed component);
- delta: buckets of the carried curves × (q1 − q_c), in bp; gamma: parallel gamma of the carried curves × Δq̄²,
  Δq̄ = mean of the Δq; residual: the rest (cross gamma, third order).
"""
import numpy as np

from ratecurves import dates as dt
from ratecurves import risk as r
from ratecurves.curves import CurveHW, instrument_6m
from ratecurves.instruments import OIS


def carried_quotes(estr, six, ois: dict, six_q: dict, day1):
    """Quotes (in %) the t0 curves would give at t1 if the forwards were realised."""
    pd1, p61 = estr.P(day1), six.P(day1)
    Pd, P6 = (lambda d: estr.P(d) / pd1), (lambda d: six.P(d) / p61)
    spot = dt.add_business_days(day1, 2)
    return ({t: OIS(spot, t).rate(Pd) * 100 for t in ois},
            {k: instrument_6m(spot, k).rate(P6, Pd) * 100 for k in six_q})


def _keys(estr, six):
    return [i.tenor for i in estr.instruments] + [r.key(i) for i in six.instruments]


def explain(swaps, day0, day1, quotes0, quotes1, fixing, cls=CurveHW, h_bp: float = 1.0) -> dict:
    """quotes0, quotes1: (OIS quotes, 6M quotes) in %, in the format of `risk.build`. Amounts in EUR."""
    e0, k0 = r.build(day0, *quotes0, cls)
    v0 = r.value(swaps, day0, e0, k0, fixing)
    qc = carried_quotes(e0, k0, *quotes0, day1)
    ec, kc = r.build(day1, *qc, cls)
    cashflows = sum(s.cashflows(day0, day1, fixing) for s in swaps)
    vp = sum(s.value(day1, kc.P, ec.P, fixing, cutoff=day0) for s in swaps)
    vc, b = r.buckets(swaps, day1, ec, kc, fixing)

    bump = lambda d: r.value(swaps, day1, *r.build(  # noqa: E731
        day1, *({k: v + d / 100 for k, v in q.items()} for q in qc), cls), fixing)
    gamma = (bump(h_bp) - 2 * vc + bump(-h_bp)) / h_bp ** 2  # EUR / bp²

    q1, q0 = {**quotes1[0], **quotes1[1]}, {**qc[0], **qc[1]}
    dq = np.array([(q1[k] - q0[k]) * 100 for k in _keys(ec, kc)])  # bp
    e1, k1 = r.build(day1, *quotes1, cls)
    v1 = r.value(swaps, day1, e1, k1, fixing)

    res = {"total": v1 + cashflows - v0, "carry": vp + cashflows - v0, "fixings": vc - vp, "delta": float(b @ dq),
           "gamma": 0.5 * gamma * dq.mean() ** 2}
    res["residual"] = res["total"] - sum(v for k, v in res.items() if k != "total")
    return res
