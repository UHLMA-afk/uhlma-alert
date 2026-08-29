
"""
UHLMA Crossover Alert - Multi-Instrument
==========================================
Bildet den TradingView-Indikator "Uhl MA Crossover System" (von alexgrover)
1:1 nach und schickt bei einer Kreuzung von CTS und CMA eine Telegram-Nachricht.
Überwacht mehrere Instrumente in einem Durchlauf: Bitcoin, Ethereum, Gold,
Silber und Apple.
 
Original Pine-Script-Logik:
    length = 500, mult = 1, src = close
 
    Var   = variance(src, length) * mult
    sma   = sma(src, length)
 
    secma = (sma - cma[1])^2   (0 falls cma[1] noch nicht existiert)
    sects = (src - cts[1])^2   (0 falls cts[1] noch nicht existiert)
 
    ka = 1 - Var/secma   falls Var < secma,  sonst 0
    kb = 1 - Var/sects   falls Var < sects,  sonst 0
 
    cma := ka*sma + (1-ka)*cma[1]   (cma[1] Ersatzwert: src, falls noch nicht vorhanden)
    cts := kb*src + (1-kb)*cts[1]   (cts[1] Ersatzwert: src, falls noch nicht vorhanden)
 
    Signal: CTS kreuzt CMA (in beide Richtungen)
"""
 
import os
import requests
import numpy as np
import pandas as pd
import yfinance as yf
 
# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
INTERVAL = os.environ.get("INTERVAL", "15m")   # muss zu deinem TradingView-Intervall passen
LENGTH = int(os.environ.get("LENGTH", "500"))
MULT = float(os.environ.get("MULT", "1.0"))
 
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
 
# data-api.binance.vision ist Binances offizielle Marktdaten-API. Sie liefert
# dieselben Kursdaten wie api.binance.com, wird aber (anders als api.binance.com)
# i.d.R. nicht für Cloud-/Rechenzentrums-IPs wie z.B. GitHub Actions blockiert.
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
 
# Hier trägst du ein, was überwacht werden soll.
# source: "binance" (Krypto, sehr zuverlässig) oder "yfinance" (Aktien/Rohstoffe)
INSTRUMENTS = [
    {"display": "Bitcoin",  "source": "binance",  "symbol": "BTCUSDT"},
    {"display": "Ethereum", "source": "binance",  "symbol": "ETHUSDT"},
    {"display": "Gold",     "source": "yfinance", "symbol": "GC=F"},
    {"display": "Silber",   "source": "yfinance", "symbol": "SI=F"},
    {"display": "Apple",    "source": "yfinance", "symbol": "AAPL"},
]
 
 
# ---------------------------------------------------------------------------
# Kursdaten holen: Binance (Krypto)
# Pine's variance()-Funktion ist eine verschachtelte SMA und braucht daher
# rund 2*length Bars Vorlauf, bis der Indikator überhaupt Werte liefert.
# Da Binance pro Anfrage max. 1000 Kerzen liefert, wird bei Bedarf paginiert.
# ---------------------------------------------------------------------------
def get_closes_binance(symbol: str, interval: str, min_bars: int) -> pd.Series:
    all_rows = []
    end_time = None
    per_request = 1000
 
    while len(all_rows) < min_bars:
        params = {"symbol": symbol, "interval": interval, "limit": per_request}
        if end_time is not None:
            params["endTime"] = end_time
        resp = requests.get(BINANCE_URL, params=params, timeout=15)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows = batch + all_rows
        end_time = batch[0][0] - 1
        if len(batch) < per_request:
            break
 
    seen = {row[0]: row for row in all_rows}
    rows_sorted = [seen[k] for k in sorted(seen.keys())]
    closes = [float(row[4]) for row in rows_sorted]
    close_times = [pd.to_datetime(row[6], unit="ms") for row in rows_sorted]
    return pd.Series(closes, index=close_times, name="close")
 
 
# ---------------------------------------------------------------------------
# Kursdaten holen: Yahoo Finance (Aktien, Rohstoffe)
# ---------------------------------------------------------------------------
def get_closes_yfinance(symbol: str, interval: str) -> pd.Series:
    # Yahoo erlaubt bei Intraday-Kerzen (z.B. 15m) max. ca. 60 Tage Historie
    intraday = interval in ("1m", "2m", "5m", "15m", "30m", "60m", "90m")
    period = "60d" if intraday else "2y"
    df = yf.download(tickers=symbol, period=period, interval=interval,
                      progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"Keine Daten für {symbol} von Yahoo Finance erhalten")
    closes = df["Close"]
    if isinstance(closes, pd.DataFrame):  # bei manchen yfinance-Versionen MultiIndex
        closes = closes.iloc[:, 0]
    return closes.dropna()
 
 
def get_closes(instrument: dict, interval: str, min_bars: int) -> pd.Series:
    if instrument["source"] == "binance":
        return get_closes_binance(instrument["symbol"], interval, min_bars)
    elif instrument["source"] == "yfinance":
        return get_closes_yfinance(instrument["symbol"], interval)
    else:
        raise ValueError(f"Unbekannte Quelle: {instrument['source']}")
 
 
# ---------------------------------------------------------------------------
# UHLMA-Berechnung (exakter Nachbau der Pine-Script-Logik)
# ---------------------------------------------------------------------------
def compute_uhlma(src: pd.Series, length: int, mult: float):
    n = len(src)
 
    sma = src.rolling(length).mean()
    sq_dev = (src - sma) ** 2
    var = sq_dev.rolling(length).mean() * mult  # entspricht Pine's variance()
 
    cma = pd.Series(np.nan, index=src.index)
    cts = pd.Series(np.nan, index=src.index)
 
    for i in range(n):
        if pd.isna(sma.iloc[i]) or pd.isna(var.iloc[i]):
            continue  # noch nicht genug Bars für length
 
        prev_cma = cma.iloc[i - 1] if i > 0 else np.nan
        prev_cts = cts.iloc[i - 1] if i > 0 else np.nan
 
        diff_cma = (sma.iloc[i] - prev_cma) if not pd.isna(prev_cma) else 0.0
        diff_cts = (src.iloc[i] - prev_cts) if not pd.isna(prev_cts) else 0.0
        secma = diff_cma ** 2
        sects = diff_cts ** 2
 
        Var = var.iloc[i]
        ka = (1 - Var / secma) if (secma != 0 and Var < secma) else 0.0
        kb = (1 - Var / sects) if (sects != 0 and Var < sects) else 0.0
 
        cma_prev_for_calc = prev_cma if not pd.isna(prev_cma) else src.iloc[i]
        cts_prev_for_calc = prev_cts if not pd.isna(prev_cts) else src.iloc[i]
 
        cma.iloc[i] = ka * sma.iloc[i] + (1 - ka) * cma_prev_for_calc
        cts.iloc[i] = kb * src.iloc[i] + (1 - kb) * cts_prev_for_calc
 
    return cma, cts
 
 
# ---------------------------------------------------------------------------
# Telegram-Benachrichtigung
# ---------------------------------------------------------------------------
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("WARNUNG: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID nicht gesetzt. Nachricht nicht gesendet:")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    resp.raise_for_status()
 
 
# ---------------------------------------------------------------------------
# Ein Instrument prüfen
# ---------------------------------------------------------------------------
def check_instrument(instrument: dict):
    display = instrument["display"]
    required_bars = 2 * LENGTH + 20
 
    try:
        closes = get_closes(instrument, INTERVAL, min_bars=required_bars + 1)
    except Exception as e:
        print(f"[{display}] Fehler beim Laden der Kursdaten: {e}")
        return
 
    closes = closes.iloc[:-1]  # letzte (evtl. noch offene) Kerze verwerfen
 
    if len(closes) < required_bars:
        print(f"[{display}] Nicht genug Kursdaten ({len(closes)} von benötigten {required_bars}).")
        return
 
    cma, cts = compute_uhlma(closes, LENGTH, MULT)
 
    cts_prev, cts_now = cts.iloc[-2], cts.iloc[-1]
    cma_prev, cma_now = cma.iloc[-2], cma.iloc[-1]
 
    if pd.isna(cts_prev) or pd.isna(cma_prev):
        print(f"[{display}] Noch nicht genug berechnete Werte für einen Vergleich.")
        return
 
    crossed_up = cts_prev <= cma_prev and cts_now > cma_now
    crossed_down = cts_prev >= cma_prev and cts_now < cma_now
 
    price = closes.iloc[-1]
    ts = closes.index[-1]
 
    if crossed_up:
        msg = (f"📈 UHLMA CROSS (bullish)\n"
               f"{display} ({instrument['symbol']}) {INTERVAL}\n"
               f"Kurs: {price:.2f}\n"
               f"CTS: {cts_now:.2f} > CMA: {cma_now:.2f}\n"
               f"Zeit (Kerzenschluss): {ts}")
        print(msg)
        send_telegram(msg)
    elif crossed_down:
        msg = (f"📉 UHLMA CROSS (bearish)\n"
               f"{display} ({instrument['symbol']}) {INTERVAL}\n"
               f"Kurs: {price:.2f}\n"
               f"CTS: {cts_now:.2f} < CMA: {cma_now:.2f}\n"
               f"Zeit (Kerzenschluss): {ts}")
        print(msg)
        send_telegram(msg)
    else:
        print(f"[{display}] Kein Crossover. CTS={cts_now:.2f} CMA={cma_now:.2f} (Zeit: {ts})")
 
 
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Test-Modus: sendet sofort eine Testnachricht, ohne echte Daten zu prüfen.
    if os.environ.get("TEST_MODE", "").lower() == "true":
        names = ", ".join(i["display"] for i in INSTRUMENTS)
        msg = (f"✅ Testnachricht\n"
               f"Dein UHLMA-Alert-Bot ist korrekt eingerichtet!\n"
               f"Überwachte Instrumente: {names}\n"
               f"Intervall: {INTERVAL}")
        print(msg)
        send_telegram(msg)
        return
 
    for instrument in INSTRUMENTS:
        check_instrument(instrument)
 
 
if __name__ == "__main__":
    main()
 
