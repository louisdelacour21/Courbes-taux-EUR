"""Morning briefing: consistency with the risk and PnL explain modules."""
from datetime import date

from ratecurves import briefing as br


def test_briefing_on_the_basis_jump_day():
    s = br.briefing(date(2026, 5, 4))  # first day of the +2.5 bp basis jump on the 10Y IRS
    assert s["prev_day"] < s["day"]
    assert [abs(x) for _, x in s["top3"]] == sorted((abs(x) for _, x in s["top3"]), reverse=True)
    assert abs(sum(v for k, v in s["pnl"].items() if k != "total") - s["pnl"]["total"]) < 1e-6
    assert any("IRS 10Y" in a for a in s["alerts"])
    assert "Top 3 pillars" in br.text(s)
