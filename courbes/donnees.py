"""Séries BCE téléchargées depuis l'API publique et gratuite data-api.ecb.europa.eu, mises en cache dans data/bce/.

Le cache est versionné : les tests et la CI tournent sans réseau. `serie(nom, refresh=True)` retélécharge.
"""
import io
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

# fenêtre des cotations reconstituées (un an) ; les séries partent du 1er du mois pour ancrer la base EURIBOR
DEBUT, FIN = date(2025, 10, 30), date(2026, 10, 29)
API = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata&startPeriod={start}&endPeriod={end}"
CACHE = Path(__file__).resolve().parent.parent / "data" / "bce"

_AAA = "YC.B.U2.EUR.4F.G_N_A.SV_C_YM."
SERIES = {
    "estr": "EST.B.EU000A2X2A25.WT",               # €STR, % ACT/360
    "dfr": "FM.D.U2.EUR.4F.KR.DFR.LEV",            # taux de la facilité de dépôt, %
    "euribor6m": "FM.M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA",  # moyenne mensuelle EURIBOR 6M, %
    **{p.lower(): _AAA + p for p in ("BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2", "SR_3M", "SR_1Y", "SR_5Y", "SR_10Y", "SR_30Y")},
}


def serie(nom: str, refresh: bool = False) -> pd.Series:
    """Série BCE indexée par date (journalière) ou par "AAAA-MM" (mensuelle)."""
    code = SERIES[nom]
    path = CACHE / f"{code}.csv"
    if refresh or not path.exists():
        flow, key = code.split(".", 1)
        url = API.format(flow=flow, key=key, start=DEBUT.replace(day=1), end=FIN)
        with urllib.request.urlopen(url, timeout=60) as r:
            df = pd.read_csv(io.BytesIO(r.read()), usecols=["TIME_PERIOD", "OBS_VALUE"])
        CACHE.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    df = pd.read_csv(path, dtype={"TIME_PERIOD": str})
    if len(df.TIME_PERIOD.iloc[0]) == 10:
        df.TIME_PERIOD = pd.to_datetime(df.TIME_PERIOD).dt.date
    return df.set_index("TIME_PERIOD").OBS_VALUE.rename(nom)
