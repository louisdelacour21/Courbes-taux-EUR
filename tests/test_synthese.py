"""Synthèse du matin : cohérence avec les modules de risque et de PnL explain."""
from datetime import date

from courbes import synthese as sy


def test_synthese_du_jour_de_fixing_du_saut():
    s = sy.synthese(date(2026, 5, 4))  # premier jour du saut de base +2,5 bp sur l'IRS 10Y
    assert s["veille"] < s["jour"]
    assert [abs(x) for _, x in s["top3"]] == sorted((abs(x) for _, x in s["top3"]), reverse=True)
    assert abs(sum(v for k, v in s["pnl"].items() if k != "total") - s["pnl"]["total"]) < 1e-6
    assert any("IRS 10Y" in a for a in s["alertes"])
    assert "Top 3 piliers" in sy.texte(s)
