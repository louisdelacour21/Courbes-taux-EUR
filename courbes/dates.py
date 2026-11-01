"""Dates de marché EUR : calendrier TARGET, jours ouvrés, ténors, décompte des jours, échéanciers.

Référence : QuantLib (ql.TARGET, ql.Actual360, ql.Actual365Fixed, ql.Thirty360 BondBasis, ql.Schedule
en génération backward). Reproduit au jour près sur 2000-2060 — voir tests/test_dates.py.

Conventions de jour ouvré : "F" following, "MF" modified following, "P" preceding,
"MP" modified preceding, "U" non ajusté.
"""
import calendar as _cal
from datetime import date, timedelta
from functools import lru_cache

ONE_DAY = timedelta(days=1)


def easter_sunday(y: int) -> date:
    """Dimanche de Pâques grégorien (algorithme de Meeus/Jones/Butcher)."""
    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(y, month, day + 1)


@lru_cache(maxsize=None)
def target_holidays(y: int) -> frozenset:
    """Jours fériés TARGET2 de l'année y (hors week-ends)."""
    easter_monday = easter_sunday(y) + ONE_DAY
    h = {date(y, 1, 1), date(y, 12, 25)}
    if y >= 2000:
        h |= {easter_monday - 3 * ONE_DAY, easter_monday, date(y, 5, 1), date(y, 12, 26)}
    if y in (1998, 1999, 2001):  # fermetures exceptionnelles du 31/12, comme QuantLib
        h.add(date(y, 12, 31))
    return frozenset(h)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in target_holidays(d.year)


def adjust(d: date, conv: str = "MF") -> date:
    if conv == "U":
        return d
    step = ONE_DAY if conv in ("F", "MF") else -ONE_DAY
    a = d
    while not is_business_day(a):
        a += step
    if conv in ("MF", "MP") and a.month != d.month:
        return adjust(d, "P" if conv == "MF" else "F")
    return a


def last_day_of_month(d: date) -> date:
    return date(d.year, d.month, _cal.monthrange(d.year, d.month)[1])


def is_end_of_month(d: date) -> bool:
    """Dernier jour ouvré du mois (au sens du calendrier TARGET)."""
    return d.month != adjust(d + ONE_DAY, "F").month


def end_of_month(d: date) -> date:
    """Dernier jour ouvré du mois de d."""
    return adjust(last_day_of_month(d), "P")


def add_business_days(d: date, n: int) -> date:
    if n == 0:
        return adjust(d, "F")
    step = 1 if n > 0 else -1
    while n:
        d += step * ONE_DAY
        if is_business_day(d):
            n -= step
    return d


def add_months(d: date, n: int) -> date:
    """Ajout calendaire de n mois, jour ramené au dernier jour du mois si besoin (31/01 + 1M = 28 ou 29/02)."""
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, _cal.monthrange(y, m)[1]))


def parse_tenor(tenor: str) -> tuple[int, str]:
    """"6M" -> (6, "M"). Unités : D (jours ouvrés), W, M, Y."""
    n, unit = int(tenor[:-1]), tenor[-1].upper()
    if unit not in "DWMY":
        raise ValueError(f"ténor inconnu : {tenor!r}")
    return n, unit


def advance(d: date, tenor: str, conv: str = "MF", eom: bool = False) -> date:
    """Équivalent de ql.TARGET().advance(d, ténor, conv, eom)."""
    n, unit = parse_tenor(tenor)
    if unit == "D":
        return adjust(d, conv) if n == 0 else add_business_days(d, n)
    if unit == "W":
        return adjust(d + timedelta(weeks=n), conv)
    d1 = add_months(d, n * 12 if unit == "Y" else n)
    if eom and is_end_of_month(d):
        return end_of_month(d1)
    return adjust(d1, conv)


def year_fraction(d1: date, d2: date, basis: str) -> float:
    """Fraction d'année entre d1 et d2 : "ACT/360", "ACT/365F" ou "30/360" (Bond Basis, ISDA 2006 4.16(f))."""
    if basis == "ACT/360":
        return (d2 - d1).days / 360
    if basis == "ACT/365F":
        return (d2 - d1).days / 365
    if basis == "30/360":
        dd1, dd2 = d1.day, d2.day
        if dd1 == 31:
            dd1 = 30
        if dd2 == 31 and dd1 == 30:
            dd2 = 30
        return (360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + dd2 - dd1) / 360
    raise ValueError(f"base inconnue : {basis!r}")


def schedule(effective: date, termination: date, tenor: str, conv: str = "MF", eom: bool = False) -> list[date]:
    """Échéancier généré à rebours depuis la maturité (stub court en tête), comme ql.Schedule
    en DateGeneration.Backward, avec la même convention pour les dates intermédiaires et la maturité.
    """
    n, unit = parse_tenor(tenor)
    if unit not in "MY":
        raise ValueError("échéancier : ténor en mois ou en années uniquement")
    months = n * 12 if unit == "Y" else n
    calendar_eom = termination == last_day_of_month(termination)

    # génération sur le calendrier « nul » (tous les jours ouvrés), comme QuantLib
    dates = [termination]
    i = 1
    while True:
        temp = add_months(termination, -i * months)
        if eom and calendar_eom:
            temp = last_day_of_month(temp)
        if temp < effective:
            break
        if temp != dates[-1]:
            dates.append(temp)
        i += 1
    if adjust(dates[-1], conv) != adjust(effective, conv):
        dates.append(effective)
    dates.reverse()

    if eom and is_end_of_month(termination):
        # comportement QuantLib 1.44 : dates intermédiaires = dernier jour calendaire du mois, puis ajustées
        # (en "F", le 31/10 dimanche devient le 01/11) ; départ et maturité simplement ajustés
        dates[1:-1] = [last_day_of_month(x) for x in dates[1:-1]]
    dates = [adjust(x, conv) for x in dates]

    # une date intermédiaire peut rejoindre une extrémité après ajustement : on la retire
    if len(dates) >= 2 and dates[-2] >= dates[-1]:
        dates[-2] = dates[-1]
        dates.pop()
    if len(dates) >= 2 and dates[1] <= dates[0]:
        dates[1] = dates[0]
        dates.pop(0)
    return dates
