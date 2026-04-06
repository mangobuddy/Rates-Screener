"""
Data fetching for overnight benchmark rates and government bond yield curves.
Each fetch_<ccy>() returns:
  {
    "overnight": {"name": str, "rate": float|None, "date": str|None},
    "curve": {"tenors": [str], "years": [float], "yields": [float], "date": str|None},
  }
"""
import requests
import pandas as pd
import logging
from datetime import datetime, timedelta
from io import StringIO

from src.config import FRED_API_KEY, TENOR_TO_YEARS, CURRENCIES

logger = logging.getLogger(__name__)
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "RatesScreenerBot/1.0"})
_TIMEOUT = 20


# ═══════════════════════════════════════════════
#  FRED helper (backbone for USD + fallbacks)
# ═══════════════════════════════════════════════

def _fred(series_id: str):
    """Latest non-null FRED observation → (value, date) or (None, None)."""
    try:
        r = _SESSION.get("https://api.stlouisfed.org/fred/series/observations", params={
            "series_id": series_id, "api_key": FRED_API_KEY,
            "file_type": "json", "sort_order": "desc", "limit": 10,
        }, timeout=_TIMEOUT)
        r.raise_for_status()
        for o in r.json().get("observations", []):
            if o["value"] != ".":
                return float(o["value"]), o["date"]
    except Exception as e:
        logger.warning(f"FRED {series_id}: {e}")
    return None, None


def _fred_curve(series_map: dict) -> dict:
    """Build a curve from multiple FRED series. {tenor_label: series_id}."""
    tenors, years, vals, date = [], [], [], None
    for t, sid in series_map.items():
        v, d = _fred(sid)
        y = TENOR_TO_YEARS.get(t)
        if v is not None and y is not None:
            tenors.append(t); years.append(y); vals.append(v)
            if d and (date is None or d > date):
                date = d
    return _sort_curve(tenors, years, vals, date)


def _sort_curve(tenors, years, vals, date):
    if not tenors:
        return {"tenors": [], "years": [], "yields": [], "date": date}
    order = sorted(range(len(years)), key=lambda i: years[i])
    return {
        "tenors": [tenors[i] for i in order],
        "years": [years[i] for i in order],
        "yields": [vals[i] for i in order],
        "date": date,
    }


# ═══════════════════════════════════════════════
#  USD — SOFR (NY Fed) + UST (FRED)
# ═══════════════════════════════════════════════

def fetch_usd() -> dict:
    # Overnight: SOFR from NY Fed
    overnight = {"name": "SOFR", "rate": None, "date": None}
    try:
        r = _SESSION.get("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json", timeout=_TIMEOUT)
        r.raise_for_status()
        rec = r.json()["refRates"][0]
        overnight = {"name": "SOFR", "rate": float(rec["percentRate"]), "date": rec["effectiveDate"]}
    except Exception as e:
        logger.warning(f"SOFR: {e}")
        v, d = _fred("SOFR")
        if v: overnight = {"name": "SOFR", "rate": v, "date": d}

    # Curve: full UST from FRED
    curve = _fred_curve({
        "1M": "DGS1MO", "3M": "DGS3MO", "6M": "DGS6MO",
        "1Y": "DGS1", "2Y": "DGS2", "3Y": "DGS3", "5Y": "DGS5",
        "7Y": "DGS7", "10Y": "DGS10", "20Y": "DGS20", "30Y": "DGS30",
    })
    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  EUR — €STR (ECB) + Euro AAA yield curve (ECB)
# ═══════════════════════════════════════════════

def fetch_eur() -> dict:
    # Overnight: €STR
    overnight = {"name": "€STR", "rate": None, "date": None}
    try:
        url = "https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT?lastNObservations=1&format=csvdata"
        r = _SESSION.get(url, timeout=_TIMEOUT)
        if r.status_code == 200:
            df = pd.read_csv(StringIO(r.text))
            if not df.empty and "OBS_VALUE" in df.columns:
                overnight = {"name": "€STR", "rate": float(df["OBS_VALUE"].iloc[-1]),
                             "date": str(df["TIME_PERIOD"].iloc[-1])}
    except Exception as e:
        logger.warning(f"€STR: {e}")

    # Curve: ECB AAA govt yield curve (spot rates)
    ecb_tenors = {
        "3M": "SR_0Y3M", "6M": "SR_0Y6M", "1Y": "SR_1Y", "2Y": "SR_2Y",
        "3Y": "SR_3Y", "5Y": "SR_5Y", "7Y": "SR_7Y", "10Y": "SR_10Y",
        "15Y": "SR_15Y", "20Y": "SR_20Y", "30Y": "SR_30Y",
    }
    tenors, years, vals, date = [], [], [], None
    for t, ecb_key in ecb_tenors.items():
        try:
            url = f"https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.{ecb_key}?lastNObservations=1&format=csvdata"
            r = _SESSION.get(url, timeout=_TIMEOUT)
            if r.status_code == 200:
                df = pd.read_csv(StringIO(r.text))
                if not df.empty and "OBS_VALUE" in df.columns:
                    v = float(df["OBS_VALUE"].iloc[-1])
                    d = str(df["TIME_PERIOD"].iloc[-1]) if "TIME_PERIOD" in df.columns else None
                    y = TENOR_TO_YEARS.get(t)
                    if y:
                        tenors.append(t); years.append(y); vals.append(v)
                        if d and (date is None or d > date): date = d
        except Exception:
            continue
    curve = _sort_curve(tenors, years, vals, date)
    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  GBP — SONIA + UK Gilts (BoE database)
# ═══════════════════════════════════════════════

def fetch_gbp() -> dict:
    overnight = {"name": "SONIA", "rate": None, "date": None}
    # SONIA via BoE database series IUDSOIA
    try:
        today = datetime.now().strftime("%d/%b/%Y")
        week_ago = (datetime.now() - timedelta(days=14)).strftime("%d/%b/%Y")
        url = f"https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&SeriesCodes=IUDSOIA&CSVF=CN&UsingCodes=Y&VPD=Y&VFD={week_ago}"
        r = _SESSION.get(url, timeout=_TIMEOUT)
        if r.status_code == 200 and "DATE" in r.text.upper():
            df = pd.read_csv(StringIO(r.text))
            if not df.empty:
                last = df.dropna().iloc[-1]
                overnight = {"name": "SONIA", "rate": float(last.iloc[-1]), "date": str(last.iloc[0])}
    except Exception as e:
        logger.warning(f"SONIA BoE: {e}")
        v, d = _fred("IUDSOIA")
        if v: overnight = {"name": "SONIA", "rate": v, "date": d}

    # Gilt yields — BoE nominal spot curve series
    # Series codes: IUDSNPY = nominal par yield at N years
    boe_series = {
        "1Y": "IUMALNPY", "2Y": "IUDMNPY", "3Y": "IUDMNPY",
        "5Y": "IUDMNPY", "7Y": "IUDMNPY", "10Y": "IUDMNPY",
        "15Y": "IUDMNPY", "20Y": "IUDMNPY", "25Y": "IUDMNPY",
    }
    # BoE series are complex; fall back to FRED for reliable data
    curve_series = {}
    # FRED carries some UK data
    fred_uk = {"10Y": "IRLTLT01GBD156N"}
    curve = _fred_curve(fred_uk)

    # Try to enrich with BoE gilt benchmark yields from their CSV
    try:
        week_ago = (datetime.now() - timedelta(days=14)).strftime("%d/%b/%Y")
        # Key gilt yield series from BoE: nominal par yields
        codes = "IUDMNPY,IUDSNPY,IUDLNPY,IUAMNPY,IUDMNZC,IUDSNZC"
        url = f"https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&SeriesCodes={codes}&CSVF=CN&UsingCodes=Y&VPD=Y&VFD={week_ago}"
        r = _SESSION.get(url, timeout=_TIMEOUT)
        if r.status_code == 200 and len(r.text) > 100:
            df = pd.read_csv(StringIO(r.text))
            if not df.empty:
                last = df.dropna(how="all").iloc[-1]
                # Parse whatever columns are available
                tenors_found, years_found, vals_found = [], [], []
                for col in df.columns[1:]:
                    try:
                        v = float(last[col])
                        col_l = col.upper()
                        # Try to identify tenor from column name
                        for t_str, y_val in TENOR_TO_YEARS.items():
                            if t_str.lower().replace("y","year") in col_l.lower().replace(" ",""):
                                tenors_found.append(t_str)
                                years_found.append(y_val)
                                vals_found.append(v)
                                break
                    except (ValueError, TypeError):
                        continue
                if len(tenors_found) > len(curve["tenors"]):
                    curve = _sort_curve(tenors_found, years_found, vals_found, str(last.iloc[0]))
    except Exception as e:
        logger.debug(f"BoE enrichment: {e}")

    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  JPY — TONA + JGB (Ministry of Finance Japan)
# ═══════════════════════════════════════════════

def fetch_jpy() -> dict:
    overnight = {"name": "TONA", "rate": None, "date": None}
    v, d = _fred("IRSTCI01JPD156N")
    if v: overnight = {"name": "TONA", "rate": v, "date": d}

    # JGB yields from MoF Japan — daily CSV
    curve = {"tenors": [], "years": [], "yields": [], "date": None}
    try:
        url = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcm_all.csv"
        r = _SESSION.get(url, timeout=_TIMEOUT)
        if r.status_code == 200:
            text = r.text
            lines = text.strip().split("\n")
            # The CSV has a header row and data rows; find the right structure
            # Try reading with pandas, skip bad rows
            for skip in range(0, 5):
                try:
                    df = pd.read_csv(StringIO(text), skiprows=skip, encoding="utf-8", on_bad_lines="skip")
                    if len(df.columns) >= 5 and len(df) > 10:
                        break
                except Exception:
                    continue

            if not df.empty:
                last = df.iloc[-1]
                date_val = str(last.iloc[0]).strip()

                # Column headers typically: Date, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 15Y, 20Y, 25Y, 30Y, 40Y
                tenor_map = {
                    "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10,
                    "15Y": 15, "20Y": 20, "25Y": 25, "30Y": 30, "40Y": 40,
                }
                tenors, years, vals = [], [], []
                for col in df.columns[1:]:
                    col_s = str(col).strip().upper().replace(" ", "")
                    # Try to match column name to a tenor
                    matched_tenor = None
                    for t in tenor_map:
                        # Match "1Y", "1 Year", "1year", etc.
                        num = t.replace("Y", "")
                        if col_s == t or col_s == num + "YEAR" or col_s == num + "YEARS":
                            matched_tenor = t
                            break
                        if num + "Y" in col_s and len(col_s) <= len(num) + 5:
                            matched_tenor = t
                            break
                    if matched_tenor is None:
                        # Try positional matching for standard MoF format
                        col_idx = list(df.columns).index(col)
                        positional_tenors = [None, "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "25Y", "30Y", "40Y"]
                        if col_idx < len(positional_tenors):
                            matched_tenor = positional_tenors[col_idx]

                    if matched_tenor and matched_tenor in tenor_map:
                        try:
                            v = float(last[col])
                            tenors.append(matched_tenor)
                            years.append(tenor_map[matched_tenor])
                            vals.append(v)
                        except (ValueError, TypeError):
                            pass

                curve = _sort_curve(tenors, years, vals, date_val)
    except Exception as e:
        logger.warning(f"MoF Japan: {e}")
        # Fallback
        v10, d10 = _fred("IRLTLT01JPM156N")
        if v10:
            curve = {"tenors": ["10Y"], "years": [10.0], "yields": [v10], "date": d10}

    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  CHF — SARON + Swiss Confederation bonds (SNB)
# ═══════════════════════════════════════════════

def fetch_chf() -> dict:
    overnight = {"name": "SARON", "rate": None, "date": None}
    # SNB data portal — try FRED fallback
    v, d = _fred("IRSTCI01CHD156N")
    if v is None:
        v, d = _fred("IR3TIB01CHM156N")
    if v: overnight = {"name": "SARON", "rate": v, "date": d}

    # Swiss Confederation yields — try SNB CSV API
    curve = {"tenors": [], "years": [], "yields": [], "date": None}
    try:
        # SNB provides data via their data portal
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        url = f"https://data.snb.ch/api/cube/rendoblim/data/csv/en?fromDate={week_ago}&toDate={today}"
        r = _SESSION.get(url, timeout=_TIMEOUT)
        if r.status_code == 200 and len(r.text) > 100:
            df = pd.read_csv(StringIO(r.text), sep=";", on_bad_lines="skip")
            if not df.empty:
                # Parse SNB format — columns typically include Date, D0 (dimension), Value
                tenors, years, vals = [], [], []
                date_str = None
                # Group by date, take latest
                for _, row in df.iterrows():
                    pass  # SNB format needs specific parsing
    except Exception as e:
        logger.debug(f"SNB: {e}")

    # Fallback: FRED
    if not curve["tenors"]:
        fred_ch = {"10Y": "IRLTLT01CHM156N"}
        curve = _fred_curve(fred_ch)

    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  CAD — CORRA + Canada Govt (BoC Valet API)
# ═══════════════════════════════════════════════

def fetch_cad() -> dict:
    overnight = {"name": "CORRA", "rate": None, "date": None}
    try:
        r = _SESSION.get("https://www.bankofcanada.ca/valet/observations/AVG.INTWO/json?recent=1", timeout=_TIMEOUT)
        if r.status_code == 200:
            obs = r.json().get("observations", [])
            if obs:
                rec = obs[-1]
                overnight = {"name": "CORRA", "rate": float(rec["AVG.INTWO"]["v"]), "date": rec["d"]}
    except Exception as e:
        logger.warning(f"CORRA: {e}")

    # Bond yields via Valet API
    boc_series = {
        "2Y": "BD.CDN.2YR.DQ.YLD", "3Y": "BD.CDN.3YR.DQ.YLD",
        "5Y": "BD.CDN.5YR.DQ.YLD", "7Y": "BD.CDN.7YR.DQ.YLD",
        "10Y": "BD.CDN.10YR.DQ.YLD", "30Y": "BD.CDN.LONG.DQ.YLD",
    }
    tenors, years, vals, date = [], [], [], None
    for t, sid in boc_series.items():
        try:
            r = _SESSION.get(f"https://www.bankofcanada.ca/valet/observations/{sid}/json?recent=1", timeout=_TIMEOUT)
            if r.status_code == 200:
                obs = r.json().get("observations", [])
                if obs:
                    rec = obs[-1]
                    v = float(rec[sid]["v"])
                    d = rec["d"]
                    y = TENOR_TO_YEARS.get(t, 30.0 if t == "30Y" else None)
                    if y:
                        tenors.append(t); years.append(y); vals.append(v)
                        if date is None or d > date: date = d
        except Exception:
            continue
    curve = _sort_curve(tenors, years, vals, date)
    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  AUD — Cash Rate + ACGB (RBA)
# ═══════════════════════════════════════════════

def fetch_aud() -> dict:
    overnight = {"name": "Cash Rate", "rate": None, "date": None}
    v, d = _fred("IRSTCB01AUM156N")
    if v: overnight = {"name": "Cash Rate", "rate": v, "date": d}

    # ACGB yields from RBA Table F2 or FRED
    fred_au = {"2Y": "IRLTLT01AUM156N"}  # FRED only has limited AU data
    curve = _fred_curve(fred_au)

    # Try RBA F16 — yields on govt bonds
    try:
        url = "https://www.rba.gov.au/statistics/tables/csv/f16-data.csv"
        r = _SESSION.get(url, timeout=_TIMEOUT)
        if r.status_code == 200 and len(r.text) > 200:
            # RBA CSVs have header metadata; try various skip values
            for skip in range(8, 14):
                try:
                    df = pd.read_csv(StringIO(r.text), skiprows=skip, on_bad_lines="skip")
                    if len(df.columns) >= 3 and len(df) > 5:
                        break
                except Exception:
                    continue
            if not df.empty:
                last = df.dropna(how="all").iloc[-1]
                tenors_f, years_f, vals_f = [], [], []
                for col in df.columns[1:]:
                    col_l = str(col).lower()
                    for t, y in [("2Y",2),("3Y",3),("5Y",5),("10Y",10)]:
                        if t.lower().replace("y"," year") in col_l or t.lower() in col_l:
                            try:
                                vals_f.append(float(last[col]))
                                tenors_f.append(t); years_f.append(float(y))
                            except (ValueError, TypeError):
                                pass
                if len(tenors_f) > len(curve["tenors"]):
                    curve = _sort_curve(tenors_f, years_f, vals_f, str(last.iloc[0]))
    except Exception as e:
        logger.debug(f"RBA: {e}")

    # Absolute fallback
    if not curve["tenors"]:
        v10, d10 = _fred("IRLTLT01AUM156N")
        if v10:
            curve = {"tenors": ["10Y"], "years": [10.0], "yields": [v10], "date": d10}

    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  NZD — OCR + NZGB (RBNZ)
# ═══════════════════════════════════════════════

def fetch_nzd() -> dict:
    overnight = {"name": "OCR", "rate": None, "date": None}
    v, d = _fred("IRSTCB01NZM156N")
    if v: overnight = {"name": "OCR", "rate": v, "date": d}

    # NZGB yields — try RBNZ wholesale rates page
    # FRED has limited NZ data
    curve = {"tenors": [], "years": [], "yields": [], "date": None}
    try:
        # RBNZ publishes B2 daily benchmark rates
        url = "https://www.rbnz.govt.nz/statistics/series/exchange-and-interest-rates/wholesale-interest-rates"
        # This is HTML, would need scraping; use FRED fallback
        pass
    except Exception:
        pass

    v10, d10 = _fred("IRLTLT01NZM156N")
    if v10:
        curve = {"tenors": ["10Y"], "years": [10.0], "yields": [v10], "date": d10}
    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  SEK — Riksbank Rate + SGB (Riksbank API)
# ═══════════════════════════════════════════════

def fetch_sek() -> dict:
    overnight = {"name": "Riksbank Rate", "rate": None, "date": None}

    # Riksbank API for policy rate
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        url = f"https://api.riksbank.se/swea/v1/Observations/SECBREPOEFF/{week_ago}/{today}"
        r = _SESSION.get(url, timeout=_TIMEOUT, headers={"Accept": "application/json"})
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                rec = data[-1]
                overnight = {"name": "Riksbank Rate", "rate": float(rec.get("value", 0)),
                             "date": rec.get("date", "")}
    except Exception as e:
        logger.debug(f"Riksbank rate: {e}")
        v, d = _fred("IRSTCI01SED156N")
        if v: overnight = {"name": "Riksbank Rate", "rate": v, "date": d}

    # SGB yields from Riksbank API
    tenors, years, vals, date = [], [], [], None
    riksbank_series = {
        "2Y": "SEGVB2YC", "5Y": "SEGVB5YC", "7Y": "SEGVB7YC", "10Y": "SEGVB10YC",
    }
    for t, sid in riksbank_series.items():
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            week_ago = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
            url = f"https://api.riksbank.se/swea/v1/Observations/{sid}/{week_ago}/{today}"
            r = _SESSION.get(url, timeout=_TIMEOUT, headers={"Accept": "application/json"})
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    rec = data[-1]
                    v = float(rec.get("value", 0))
                    d = rec.get("date", "")
                    y = TENOR_TO_YEARS.get(t)
                    if y and v != 0:
                        tenors.append(t); years.append(y); vals.append(v)
                        if d and (date is None or d > date): date = d
        except Exception:
            continue

    curve = _sort_curve(tenors, years, vals, date)
    if not curve["tenors"]:
        v10, d10 = _fred("IRLTLT01SEM156N")
        if v10: curve = {"tenors": ["10Y"], "years": [10.0], "yields": [v10], "date": d10}

    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  NOK — NOWA + NGB (Norges Bank)
# ═══════════════════════════════════════════════

def fetch_nok() -> dict:
    overnight = {"name": "NOWA", "rate": None, "date": None}
    v, d = _fred("IRSTCI01NOD156N")
    if v is None:
        v, d = _fred("IR3TIB01NOM156N")
    if v: overnight = {"name": "NOWA", "rate": v, "date": d}

    # Norges Bank bond yields — FRED fallback
    curve = {"tenors": [], "years": [], "yields": [], "date": None}

    # Try Norges Bank API
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        series_map = {"3Y": "b_gbon_y3", "5Y": "b_gbon_y5", "10Y": "b_gbon_y10"}
        tenors, years, vals, date = [], [], [], None
        for t, sid in series_map.items():
            url = f"https://data.norges-bank.no/api/data/IR/{sid}/?format=csv&startPeriod={week_ago}&endPeriod={today}&locale=en"
            r = _SESSION.get(url, timeout=_TIMEOUT)
            if r.status_code == 200 and len(r.text) > 50:
                df = pd.read_csv(StringIO(r.text), sep=";", on_bad_lines="skip")
                if not df.empty:
                    last = df.iloc[-1]
                    for col in df.columns:
                        if "obs_value" in col.lower() or "value" in col.lower():
                            try:
                                v = float(last[col])
                                y = TENOR_TO_YEARS.get(t)
                                if y:
                                    tenors.append(t); years.append(y); vals.append(v)
                                    d_col = [c for c in df.columns if "period" in c.lower() or "date" in c.lower()]
                                    if d_col:
                                        d = str(last[d_col[0]])
                                        if date is None or d > date: date = d
                            except (ValueError, TypeError):
                                pass
                            break
        if tenors:
            curve = _sort_curve(tenors, years, vals, date)
    except Exception as e:
        logger.debug(f"Norges Bank: {e}")

    if not curve["tenors"]:
        v10, d10 = _fred("IRLTLT01NOM156N")
        if v10: curve = {"tenors": ["10Y"], "years": [10.0], "yields": [v10], "date": d10}

    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  SGD — SORA + SGS (MAS)
# ═══════════════════════════════════════════════

def fetch_sgd() -> dict:
    overnight = {"name": "SORA", "rate": None, "date": None}
    curve = {"tenors": [], "years": [], "yields": [], "date": None}

    # SORA from MAS API
    try:
        url = "https://eservices.mas.gov.sg/statistics/api/v1/domesticinterestrates?rows=5&sort=end_of_day desc"
        r = _SESSION.get(url, timeout=_TIMEOUT)
        if r.status_code == 200:
            records = r.json().get("result", {}).get("records", [])
            if records:
                rec = records[0]
                sora = rec.get("sora")
                if sora is not None:
                    overnight = {"name": "SORA", "rate": float(sora), "date": rec.get("end_of_day", "")}
    except Exception as e:
        logger.warning(f"MAS SORA: {e}")

    # SGS benchmark yields from MAS API
    try:
        url = "https://eservices.mas.gov.sg/statistics/api/v1/bondsandbills/m/benchmarkpricesandyields?rows=1&sort=end_of_day desc"
        r = _SESSION.get(url, timeout=_TIMEOUT)
        if r.status_code == 200:
            records = r.json().get("result", {}).get("records", [])
            if records:
                rec = records[0]
                date_str = rec.get("end_of_day", "")
                # MAS fields: e.g. "1_year_yield", "2_year_yield", etc.
                tenor_keys = [
                    ("6M", "6_month_yield", 0.5), ("1Y", "1_year_yield", 1),
                    ("2Y", "2_year_yield", 2), ("5Y", "5_year_yield", 5),
                    ("10Y", "10_year_yield", 10), ("15Y", "15_year_yield", 15),
                    ("20Y", "20_year_yield", 20), ("30Y", "30_year_yield", 30),
                ]
                tenors, years, vals = [], [], []
                for t, key, y in tenor_keys:
                    v = rec.get(key)
                    if v is not None:
                        try:
                            tenors.append(t); years.append(y); vals.append(float(v))
                        except (ValueError, TypeError):
                            pass
                # Also try alternate field names
                if not tenors:
                    for k, v in rec.items():
                        if "yield" in k.lower() and v is not None:
                            try:
                                num = "".join(c for c in k if c.isdigit())
                                if "month" in k.lower():
                                    t = f"{num}M"; y = int(num)/12
                                elif "year" in k.lower():
                                    t = f"{num}Y"; y = float(num)
                                else:
                                    continue
                                tenors.append(t); years.append(y); vals.append(float(v))
                            except (ValueError, TypeError):
                                pass

                curve = _sort_curve(tenors, years, vals, date_str)
    except Exception as e:
        logger.warning(f"MAS SGS: {e}")

    return {"overnight": overnight, "curve": curve}


# ═══════════════════════════════════════════════
#  DISPATCHER
# ═══════════════════════════════════════════════

_DISPATCH = {
    "USD": fetch_usd, "EUR": fetch_eur, "GBP": fetch_gbp, "JPY": fetch_jpy,
    "CHF": fetch_chf, "CAD": fetch_cad, "AUD": fetch_aud, "NZD": fetch_nzd,
    "SEK": fetch_sek, "NOK": fetch_nok, "SGD": fetch_sgd,
}

def fetch_rates(ccy: str) -> dict:
    """Master fetch: returns overnight + curve for a currency."""
    ccy = ccy.upper().strip()
    if ccy not in CURRENCIES:
        return {"error": f"'{ccy}' not supported. Use: {', '.join(sorted(CURRENCIES.keys()))}"}
    try:
        data = _DISPATCH[ccy]()
        data["currency"] = ccy
        data["config"] = CURRENCIES[ccy]
        data["error"] = None
        return data
    except Exception as e:
        logger.exception(f"fetch_rates({ccy})")
        return {"currency": ccy, "config": CURRENCIES[ccy], "error": str(e),
                "overnight": {"name": CURRENCIES[ccy]["overnight"], "rate": None, "date": None},
                "curve": {"tenors": [], "years": [], "yields": [], "date": None}}
