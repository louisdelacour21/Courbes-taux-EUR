"""ECB series downloaded from the free public API data-api.ecb.europa.eu, cached in data/ecb/.

The cache is versioned: tests and CI run without network access. `series(name, refresh=True)` downloads again.
"""
import io
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

# window of the reconstructed quotes (one year); series start on the 1st of the month to anchor the EURIBOR basis
START, END = date(2025, 10, 30), date(2026, 10, 29)
API = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata&startPeriod={start}&endPeriod={end}"
CACHE = Path(__file__).resolve().parent.parent / "data" / "ecb"

_AAA = "YC.B.U2.EUR.4F.G_N_A.SV_C_YM."
SERIES = {
    "estr": "EST.B.EU000A2X2A25.WT",               # €STR, % ACT/360
    "dfr": "FM.D.U2.EUR.4F.KR.DFR.LEV",            # deposit facility rate, %
    "euribor6m": "FM.M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA",  # monthly average EURIBOR 6M, %
    **{p.lower(): _AAA + p for p in ("BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2", "SR_3M", "SR_1Y", "SR_5Y", "SR_10Y", "SR_30Y")},
}


def series(name: str, refresh: bool = False) -> pd.Series:
    """ECB series indexed by date (daily) or by "YYYY-MM" (monthly)."""
    code = SERIES[name]
    path = CACHE / f"{code}.csv"
    if refresh or not path.exists():
        flow, key = code.split(".", 1)
        url = API.format(flow=flow, key=key, start=START.replace(day=1), end=END)
        with urllib.request.urlopen(url, timeout=60) as r:
            df = pd.read_csv(io.BytesIO(r.read()), usecols=["TIME_PERIOD", "OBS_VALUE"])
        CACHE.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    df = pd.read_csv(path, dtype={"TIME_PERIOD": str})
    if len(df.TIME_PERIOD.iloc[0]) == 10:
        df.TIME_PERIOD = pd.to_datetime(df.TIME_PERIOD).dt.date
    return df.set_index("TIME_PERIOD").OBS_VALUE.rename(name)
