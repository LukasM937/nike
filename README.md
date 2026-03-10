# Nike Run Club MCP Server 🏃

Ein MCP-Server (Model Context Protocol) für Python, der Nike Run Club Trainingsdaten über die inoffizielle NRC API abruft – direkt in Claude nutzbar.

---

## Voraussetzungen

- Python 3.10+
- Ein Nike-Konto mit Trainingsdaten in Nike Run Club

---

## Installation

```bash
pip install mcp httpx
```

---

## Bearer-Token ermitteln

Nike bietet keine offizielle API. Den Token holt man sich aus dem Browser:

1. Gehe zu **https://www.nike.com/member/profile**
2. Falls eingeloggt: **ausloggen** (der Token wird beim Login-Prozess erfasst)
3. Öffne die **Browser-DevTools** (F12 oder Rechtsklick → Untersuchen)
4. Gehe zum **Network**-Tab
5. **Logge dich ein**
6. Suche in den Requests nach einem Eintrag mit `Authorization` im Header (z.B. ein Request an `api.nike.com`)
7. Kopiere den langen String nach `Bearer `

⚠️ **Wichtig:** Der Token läuft nach einigen Stunden/Tagen ab. Bei `401`-Fehlern einfach einen neuen holen.

---

## Verwendung

### Als Umgebungsvariable setzen

```bash
export NRC_TOKEN="eyJhbGc..."
python server.py
```

### In Claude Desktop einbinden

Füge folgendes in deine `claude_desktop_config.json` ein:

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nike-run-club": {
      "command": "python",
      "args": ["/absoluter/pfad/zu/server.py"],
      "env": {
        "NRC_TOKEN": "dein_bearer_token_hier"
      }
    }
  }
}
```

Danach Claude Desktop neu starten.

---

## Verfügbare Tools

| Tool | Beschreibung |
|------|-------------|
| `get_recent_runs` | Letzte Läufe abrufen (Distanz, Pace, Herzrate, Kalorien…) |
| `get_run_detail` | Detaildaten eines einzelnen Laufs inkl. GPS & Herzratenverlauf |
| `get_running_stats` | Statistiken & Trends aus mehreren Läufen |
| `get_profile` | Nike Nutzerprofil anzeigen |

---

## Beispiel-Prompts für Claude

- „Zeig mir meine letzten 5 Läufe"
- „Was war mein schnellster Lauf diese Woche?"
- „Berechne meine Gesamtdistanz der letzten 20 Läufe"
- „Zeig mir die Herzratendaten meines letzten Laufs"
- „Wie hat sich meine Pace im letzten Monat entwickelt?"

---

## Bekannte Einschränkungen

- Nike bietet **keine offizielle öffentliche API** – die Endpoints sind inoffiziell und können sich ändern
- Der Bearer-Token **läuft ab** (typisch: wenige Stunden bis Tage)
- GPS-Rohdaten werden als Anzahl der Datenpunkte ausgegeben (nicht als Karte)
- Höhendaten sind manchmal unvollständig (bekanntes NRC-API-Problem)

---

## Datenquellen

- [dailydataapps.com – NRC Python Export](https://dailydataapps.com/exporting-nike-run-club-data-with-python/)
- [nrc-exporter by yasoob](https://github.com/yasoob/nrc-exporter)
- [node-nikerunclub by jzarca01](https://github.com/jzarca01/node-nikerunclub)
