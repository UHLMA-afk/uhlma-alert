"""
UHLMA Crossover Alert
======================
Bildet den TradingView-Indikator "Uhl MA Crossover System" (von alexgrover)
1:1 nach und schickt bei einer Kreuzung von CTS und CMA eine Telegram-Nachricht.

Original Pine-Script-Logik:
    length = 500, mult = 1, src = close

    Var   = variance(src, length) * mult
    sma   = sma(src, length)

    secma = (sma - cma[1])^2   (0 falls cma[1] noch nicht existiert)
    sects = (src - cts[1])^2   (0 falls cts[1] noch nicht existiert)

    ka = 1 - Var/secma   falls Var < secma,  sonst 0
    kb = 1 - Var/sects   falls Var < sects,  sonst 0

    cma := ka*sma + (1-ka)*cma[1]   (cma[1] Ersatzwert: src, falls es noch nicht existiert)
    cts := kb*src + (1-kb)*cts[1]   (cts[1] Ersatzwert: src, falls es noch nicht existiert)

    Signal: CTS kreuzt CMA (in beide Richtungen)
"""

import os
import sys
import requests
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
SYMBOL = os.environ.get("SYMBOL", "BTCUSDT")
INTERVAL = os.environ.get("INTERVAL", "15m")   # muss zu deinem TradingView-Intervall passen
LENGTH = int(os.environ.get("LENGTH", "500"))
MULT = float(os.environ.get("MULT", "1.0"))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# data-api.binance.vision ist Binances offizielle Markdaten-API. Sie liefert
# dieselben Kursdaten wie api.binance.com, wird aber (anders als api.binance.com)
# i.d.R. nicht für Cloud-/Rechenzentrums-IPs wie z.B. GitHub Actions blockiert
# (dort tritt sonst Fehler "451 Client Error" auf).
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"


# ---------------------------------------------------------------------------
# Kursdaten holen (Binance, kein API-Key nötig)
# Pine's variance()-Funktion ist eine verschachtelte SMA und braucht daher
# rund 2*length Bars Vorlauf, bis der Indikator überhaupt Werte liefert.
# Da Binance pro Anfrage max. 1000 Kerzen liefert, wird bei Bedarf paginiert
# (über den "endTime"-Parameter rückwärts in der Zeit).
# ---------------------------------------------------------------------------
def get_closes(symbol: str, interval: str, min_bars: int) -> pd.Series:
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
        oldest_open_time = batch[0][0]
        end_time = oldest_open_time - 1  # eine Millisekunde vor dem ältesten Bar
        if len(batch) < per_request:
            break  # keine älteren Daten mehr verfügbar

    # Duplikate (falls vorhanden) entfernen und sortieren
    seen = {}
    for row in all_rows:
        seen[row[0]] = row  # open_time als Key
    rows_sorted = [seen[k] for k in sorted(seen.keys())]

    closes = [float(row[4]) for row in rows_sorted]
    close_times = [pd.to_datetime(row[6], unit="ms") for row in rows_sorted]
    return pd.Series(closes, index=close_times, name="close")


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

        # secma/sects: nz(...) -> 0 falls Vorwert fehlt
        diff_cma = (sma.iloc[i] - prev_cma) if not pd.isna(prev_cma) else 0.0
        diff_cts = (src.iloc[i] - prev_cts) if not pd.isna(prev_cts) else 0.0
        secma = diff_cma ** 2
        sects = diff_cts ** 2

        Var = var.iloc[i]
        ka = (1 - Var / secma) if (secma != 0 and Var < secma) else 0.0
        kb = (1 - Var / sects) if (sects != 0 and Var < sects) else 0.0

        # nz(cma[1], src): Ersatzwert src falls Vorwert fehlt
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
# Main
# ---------------------------------------------------------------------------
def main():
    # Vorlauf für die verschachtelte variance()-Berechnung: ~2*length + Puffer
    required_bars = 2 * LENGTH + 20
    closes = get_closes(SYMBOL, INTERVAL, min_bars=required_bars + 1)

    # Nur abgeschlossene Kerzen verwenden (die letzte Kerze läuft evtl. noch)
    closes = closes.iloc[:-1]

    if len(closes) < required_bars:
        print(f"Nicht genug Kursdaten ({len(closes)} von benötigten {required_bars}).")
        sys.exit(0)

    cma, cts = compute_uhlma(closes, LENGTH, MULT)

    # letzte zwei abgeschlossene Werte prüfen
    cts_prev, cts_now = cts.iloc[-2], cts.iloc[-1]
    cma_prev, cma_now = cma.iloc[-2], cma.iloc[-1]

    if pd.isna(cts_prev) or pd.isna(cma_prev):
        print("Noch nicht genug berechnete Werte für einen Vergleich.")
        return

    crossed_up = cts_prev <= cma_prev and cts_now > cma_now
    crossed_down = cts_prev >= cma_prev and cts_now < cma_now

    price = closes.iloc[-1]
    ts = closes.index[-1]

    if crossed_up:
        msg = (f"📈 UHLMA CROSS (bullish)\n"
               f"{SYMBOL} {INTERVAL}\n"
               f"Kurs: {price:.2f}\n"
               f"CTS: {cts_now:.2f} > CMA: {cma_now:.2f}\n"
               f"Zeit (Kerzenschluss): {ts}")
        print(msg)
        send_telegram(msg)
    elif crossed_down:
        msg = (f"📉 UHLMA CROSS (bearish)\n"
               f"{SYMBOL} {INTERVAL}\n"
               f"Kurs: {price:.2f}\n"
               f"CTS: {cts_now:.2f} < CMA: {cma_now:.2f}\n"
               f"Zeit (Kerzenschluss): {ts}")
        print(msg)
        send_telegram(msg)
    else:
        print(f"Kein Crossover. CTS={cts_now:.2f} CMA={cma_now:.2f} (Zeit: {ts})")


if __name__ == "__main__":
    main()
