# UHLMA Crossover Alert (BTCUSDT)

Überwacht den "Uhl MA Crossover System"-Indikator (500, 1) auf BTCUSDT (15m)
und schickt bei jeder Kreuzung von CTS/CMA eine Telegram-Push-Nachricht.
Läuft komplett kostenlos über GitHub Actions.

## 1. Telegram-Bot einrichten (2 Minuten)

1. In Telegram nach **@BotFather** suchen, `/newbot` senden, Namen vergeben.
2. Du bekommst einen **Token** wie `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
   → Das ist dein `TELEGRAM_TOKEN`.
3. Suche in Telegram nach dem Namen deines neu erstellten Bots und schreib ihm
   eine beliebige Nachricht (z. B. "Hallo"), damit er dich kennt.
4. Rufe im Browser folgende URL auf (Token einsetzen):
   `https://api.telegram.org/bot<DEIN_TOKEN>/getUpdates`
5. Suche im JSON nach `"chat":{"id": ...}` – diese Zahl ist deine
   `TELEGRAM_CHAT_ID`.

## 2. Repository auf GitHub anlegen

1. Neues (privates oder öffentliches) Repository auf github.com erstellen.
2. Diesen kompletten Ordner hochladen (z. B. per "Upload files" im Browser,
   oder per `git push`).

## 3. Secrets hinterlegen

Im Repository: **Settings → Secrets and variables → Actions → New repository
secret**

- `TELEGRAM_TOKEN` = dein Bot-Token aus Schritt 1
- `TELEGRAM_CHAT_ID` = deine Chat-ID aus Schritt 1

## 4. Fertig

Der Workflow (`.github/workflows/alert.yml`) läuft automatisch alle 15
Minuten (kostenlos, GitHub Actions Free-Tier reicht dafür locker). Du kannst
ihn auch manuell testen: **Actions-Tab → "UHLMA Crossover Alert" →
"Run workflow"**.

Bei Kreuzung bekommst du eine Telegram-Push-Nachricht wie:

```
📈 UHLMA CROSS (bullish)
BTCUSDT 15m
Kurs: 65432.10
CTS: 65410.22 > CMA: 65380.15
Zeit (Kerzenschluss): 2026-08-26 14:15:00
```

## Anpassen

Alles über Umgebungsvariablen in `alert.yml` steuerbar:

| Variable   | Bedeutung                          | Standard  |
|------------|-------------------------------------|-----------|
| `SYMBOL`   | Binance-Symbol                      | BTCUSDT   |
| `INTERVAL` | Kerzenintervall (`1m`,`5m`,`15m`,`1h`,`4h`,`1d` ...) | 15m |
| `LENGTH`   | UHLMA-Länge                         | 500       |
| `MULT`     | UHLMA-Multiplikator                 | 1.0       |

Wichtig: Wenn du `INTERVAL` änderst, passe auch den `cron`-Zeitplan in
`alert.yml` entsprechend an (z. B. `*/5 * * * *` für 5-Minuten-Kerzen), damit
das Skript nicht öfter läuft, als neue Kerzen entstehen.

## Hinweis

Dieses Skript ist ein technisches Hilfsmittel zur Überwachung eines
Indikators und stellt keine Anlageberatung dar. Die Berechnung wurde nach
bestem Wissen aus dem originalen Pine-Script nachgebaut, kann sich in
Rundungs-/Randfällen aber minimal vom TradingView-Original unterscheiden.
