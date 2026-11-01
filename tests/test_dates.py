"""Le moteur de dates doit reproduire QuantLib au jour près sur 2000-2060."""
import random
from datetime import date, timedelta

import pytest
import QuantLib as ql

from courbes import dates as D

START, END = date(2000, 1, 1), date(2060, 12, 31)
ALL_DAYS = [START + timedelta(days=i) for i in range((END - START).days + 1)]
TARGET = ql.TARGET()
CONV = {"F": ql.Following, "MF": ql.ModifiedFollowing, "P": ql.Preceding,
        "MP": ql.ModifiedPreceding, "U": ql.Unadjusted}
UNITS = {"D": ql.Days, "W": ql.Weeks, "M": ql.Months, "Y": ql.Years}
rng = random.Random(20261101)


def q(d):
    return ql.Date(d.day, d.month, d.year)


def py(d):
    return date(d.year(), d.month(), d.dayOfMonth())


def random_day(lo=START, hi=END):
    return lo + timedelta(days=rng.randrange((hi - lo).days + 1))


def test_easter_against_known_dates():
    assert D.easter_sunday(2024) == date(2024, 3, 31)
    assert D.easter_sunday(2025) == date(2025, 4, 20)
    assert D.easter_sunday(2038) == date(2038, 4, 25)  # Pâques la plus tardive possible


def test_business_days_every_day():
    diff = [d for d in ALL_DAYS if D.is_business_day(d) != TARGET.isBusinessDay(q(d))]
    assert diff == []


@pytest.mark.parametrize("conv", CONV)
def test_adjust_every_day(conv):
    diff = [d for d in ALL_DAYS if D.adjust(d, conv) != py(TARGET.adjust(q(d), CONV[conv]))]
    assert diff == []


def test_end_of_month_every_day():
    diff = [d for d in ALL_DAYS
            if D.is_end_of_month(d) != TARGET.isEndOfMonth(q(d))
            or D.end_of_month(d) != py(TARGET.endOfMonth(q(d)))]
    assert diff == []


@pytest.mark.parametrize("tenor", ["0D", "1D", "2D", "-2D", "1W", "2W", "1M", "3M", "6M", "1Y", "2Y", "10Y", "30Y", "-6M"])
@pytest.mark.parametrize("eom", [False, True])
def test_advance(tenor, eom):
    n, unit = D.parse_tenor(tenor)
    diff = []
    for d in ALL_DAYS[::7] + [D.last_day_of_month(x) for x in ALL_DAYS[::28]]:
        if d.year > 2030 and unit == "Y" and n >= 30:
            continue  # sortirait de la plage testée
        ours = D.advance(d, tenor, "MF", eom)
        ref = py(TARGET.advance(q(d), ql.Period(n, UNITS[unit]), ql.ModifiedFollowing, eom))
        if ours != ref:
            diff.append((d, ours, ref))
    assert diff == []


@pytest.mark.parametrize("basis,qdc", [
    ("ACT/360", ql.Actual360()),
    ("ACT/365F", ql.Actual365Fixed()),
    ("30/360", ql.Thirty360(ql.Thirty360.BondBasis)),
])
def test_year_fraction(basis, qdc):
    pairs = [(random_day(), random_day()) for _ in range(20_000)]
    # cas limites du 30/360 : fins de mois et février
    pairs += [(D.last_day_of_month(date(y, m, 1)), D.last_day_of_month(date(y2, m2, 1)))
              for y, y2 in [(2023, 2024), (2024, 2025)] for m in range(1, 13) for m2 in range(1, 13)]
    for d1, d2 in pairs:
        assert D.year_fraction(d1, d2, basis) == pytest.approx(qdc.yearFraction(q(d1), q(d2)), abs=1e-15), (d1, d2)


@pytest.mark.parametrize("conv", ["MF", "F", "P", "U"])
@pytest.mark.parametrize("eom", [False, True])
def test_schedule(conv, eom):
    diff = []
    for _ in range(1500):
        eff = random_day(START, date(2028, 12, 31))
        if rng.random() < 0.3:
            eff = D.last_day_of_month(eff) - timedelta(days=rng.randrange(3))
        years = rng.choice([1, 2, 3, 5, 7, 10, 15, 20, 30])
        months = rng.choice([0, 0, 0, 1, 4, 7])  # stub court en tête une fois sur deux
        term = D.add_months(eff, 12 * years + months)
        if eom and rng.random() < 0.5:
            term = D.last_day_of_month(term)
        tenor = rng.choice(["1M", "3M", "6M", "1Y"])
        n, unit = D.parse_tenor(tenor)
        ours = D.schedule(eff, term, tenor, conv, eom)
        ref = [py(x) for x in ql.Schedule(q(eff), q(term), ql.Period(n, UNITS[unit]), TARGET,
                                          CONV[conv], CONV[conv], ql.DateGeneration.Backward, eom)]
        if ours != ref:
            diff.append((eff, term, tenor, ours[:3], ref[:3]))
    assert diff == [], f"{len(diff)} écarts, ex. {diff[:3]}"


def test_bad_inputs():
    with pytest.raises(ValueError):
        D.parse_tenor("3Q")
    with pytest.raises(ValueError):
        D.year_fraction(START, END, "ACT/ACT")
    with pytest.raises(ValueError):
        D.schedule(START, END, "2W")
