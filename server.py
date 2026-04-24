#!/usr/bin/env python3
"""
Nike Run Club MCP Server
Verwendet: /plus/v3/activities/before_id/v3/* (Stand 2025)
Token-Refresh: automatisch via Playwright (NIKE_EMAIL + NIKE_PASSWORD),
               oder manuell via NRC_TOKEN Umgebungsvariable.
"""

import os
import asyncio
import logging
import json
import time
from datetime import datetime, timezone
from typing import Optional
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

logging.basicConfig(level=logging.INFO, stream=__import__('sys').stderr)
logger = logging.getLogger("nrc-mcp")

BASE_URL             = "https://api.nike.com"
ACTIVITIES_URL       = f"{BASE_URL}/plus/v3/activities/before_id/v3/*"
ACTIVITIES_PAGED_URL = f"{BASE_URL}/plus/v3/activities/before_id/v3/{{before_id}}"
ACTIVITY_DETAIL_URL  = f"{BASE_URL}/sport/v3/me/activity/{{activity_id}}?metrics=ALL"
TOKEN_TTL            = 55 * 60  # 55 Minuten (Nike rotiert alle 60 Min.)

app = Server("nike-run-club")

_token_cache: dict        = {"value": "", "expires_at": 0.0}
_refresh_lock: asyncio.Lock = asyncio.Lock()


# ── Token-Management ───────────────────────────────────────────────────────────

def _invalidate_token() -> None:
    _token_cache["value"]      = ""
    _token_cache["expires_at"] = 0.0


async def _refresh_via_browser() -> str:
    """Meldet sich headless bei Nike an und fängt den Bearer-Token aus einem API-Request ab."""
    async with _refresh_lock:
        # Nochmal prüfen: ein anderer Coroutine hat evtl. schon erneuert
        if _token_cache["value"] and time.time() < _token_cache["expires_at"]:
            return _token_cache["value"]

        email    = os.environ.get("NIKE_EMAIL", "").strip()
        password = os.environ.get("NIKE_PASSWORD", "").strip()
        if not email or not password:
            raise ValueError(
                "Token abgelaufen und kein automatischer Refresh möglich. "
                "Bitte NIKE_EMAIL + NIKE_PASSWORD setzen oder NRC_TOKEN manuell erneuern."
            )

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "playwright nicht installiert. "
                "Bitte: pip install playwright && playwright install chromium"
            )

        logger.info("Starte headless Browser-Login für Token-Refresh…")
        captured: list[str] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx     = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = await ctx.new_page()

            def on_request(req):
                auth = req.headers.get("authorization", "")
                if auth.startswith("Bearer ") and "api.nike.com" in req.url and not captured:
                    tok = auth.removeprefix("Bearer ").strip()
                    if tok:
                        captured.append(tok)
                        logger.info("Bearer-Token abgefangen.")

            page.on("request", on_request)

            await page.goto("https://www.nike.com/login", timeout=60_000)
            await page.fill('input[name="emailAddress"]', email)
            await page.fill('input[name="password"]',     password)
            await page.click('[data-testid="login-submit-button"]')

            # Warte auf API-Aufruf mit Token (max. 15 Sekunden)
            for _ in range(15):
                if captured:
                    break
                await asyncio.sleep(1)

            # Profil-Seite erzwingt API-Calls falls noch kein Token
            if not captured:
                await page.goto("https://www.nike.com/member/profile", timeout=30_000)
                for _ in range(10):
                    if captured:
                        break
                    await asyncio.sleep(1)

            await browser.close()

        if not captured:
            raise RuntimeError(
                "Browser-Login abgeschlossen, aber kein Bearer-Token gefunden. "
                "Login fehlgeschlagen oder Nike hat die Seitenstruktur geändert."
            )

        tok = captured[0]
        _token_cache["value"]      = tok
        _token_cache["expires_at"] = time.time() + TOKEN_TTL
        logger.info("Token erfolgreich erneuert (gültig ~55 Min.).")
        return tok


async def get_current_token() -> str:
    """Gibt den gecachten Token zurück oder refresht ihn automatisch."""
    if _token_cache["value"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["value"]

    env_tok = os.environ.get("NRC_TOKEN", "").strip().removeprefix("Bearer ").strip()
    if env_tok:
        _token_cache["value"]      = env_tok
        _token_cache["expires_at"] = time.time() + TOKEN_TTL
        logger.info("Token aus NRC_TOKEN geladen.")
        return env_tok

    return await _refresh_via_browser()


async def get_headers() -> dict:
    token = await get_current_token()
    return {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
        "User-Agent":    "Mozilla/5.0",
    }


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def unix_ms_to_iso(val) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(val) / 1000, tz=timezone.utc).isoformat() if val else None
    except Exception:
        return str(val)


def fmt_duration(ms) -> Optional[str]:
    if not ms:
        return None
    s = int(ms) // 1000
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_pace(min_per_km) -> Optional[str]:
    if not min_per_km or min_per_km <= 0:
        return None
    m   = int(min_per_km)
    sec = round((min_per_km - m) * 60)
    return f"{m}:{sec:02d} min/km"


def get_sum(summaries: list, metric: str, summary: str = "total") -> Optional[float]:
    for s in summaries:
        if isinstance(s, dict) and s.get("metric") == metric and s.get("summary") == summary:
            return s.get("value")
    return None


def parse_activity(a: dict) -> dict:
    sums = a.get("summaries", [])

    dist_km  = get_sum(sums, "distance", "total")
    dur_ms   = a.get("active_duration_ms")
    pace     = get_sum(sums, "pace", "mean")
    avg_hr   = get_sum(sums, "heart_rate", "mean")
    max_hr   = get_sum(sums, "heart_rate", "max")
    calories = get_sum(sums, "calories", "total")
    elev_up  = get_sum(sums, "ascent", "total")
    elev_dn  = get_sum(sums, "descent", "total")
    steps    = get_sum(sums, "steps", "total")
    cadence  = get_sum(sums, "cadence", "mean")

    return {
        "activity_id":      a.get("id"),
        "name":             a.get("name") or "Lauf",
        "type":             a.get("type", "run"),
        "start_time":       unix_ms_to_iso(a.get("start_epoch_ms")),
        "end_time":         unix_ms_to_iso(a.get("end_epoch_ms")),
        "distance_km":      round(dist_km, 2)      if dist_km  else None,
        "duration":         fmt_duration(dur_ms),
        "duration_ms":      dur_ms,
        "pace":             fmt_pace(pace),
        "avg_heart_rate":   round(avg_hr)           if avg_hr   else None,
        "max_heart_rate":   round(max_hr)           if max_hr   else None,
        "calories_kcal":    round(calories)         if calories else None,
        "elevation_gain_m": round(float(elev_up),1) if elev_up  else None,
        "elevation_loss_m": round(float(elev_dn),1) if elev_dn  else None,
        "steps":            round(steps)            if steps    else None,
        "avg_cadence_spm":  round(cadence)          if cadence  else None,
    }


# ── API-Aufrufe ────────────────────────────────────────────────────────────────

async def api_get_activities(limit: int = 10, activity_type: str = "run") -> list[dict]:
    headers, results, before_id = await get_headers(), [], None
    async with httpx.AsyncClient(timeout=30.0) as client:
        while len(results) < limit:
            url    = ACTIVITIES_PAGED_URL.format(before_id=before_id) if before_id else ACTIVITIES_URL
            params = {"limit": min(30, limit - len(results)), "types": activity_type, "include_deleted": "false"}
            r      = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data   = r.json()
            batch  = data.get("activities", []) if isinstance(data, dict) else []
            if not batch:
                break
            results.extend(batch)
            paging    = data.get("paging", {}) if isinstance(data, dict) else {}
            before_id = paging.get("before_id") or paging.get("after_id")
            if not before_id:
                break
    return results


async def api_get_detail(activity_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            ACTIVITY_DETAIL_URL.format(activity_id=activity_id),
            headers=await get_headers(),
        )
        r.raise_for_status()
        return r.json()


# ── Tool Definitionen ──────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_recent_runs",
            description="Ruft die letzten Läufe aus Nike Run Club ab.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit":         {"type": "integer", "default": 10, "minimum": 1, "maximum": 50,
                                      "description": "Anzahl Läufe (Standard 10, max 50)"},
                    "activity_type": {"type": "string", "default": "run",
                                      "description": "'run', 'jogging' oder 'run,jogging'"},
                },
            },
        ),
        types.Tool(
            name="get_run_detail",
            description="Detaildaten eines einzelnen Laufs (GPS, Herzrate, Pace-Verlauf). Benötigt activity_id aus get_recent_runs.",
            inputSchema={
                "type": "object",
                "properties": {"activity_id": {"type": "string"}},
                "required": ["activity_id"],
            },
        ),
        types.Tool(
            name="get_running_stats",
            description="Statistiken aus den letzten Läufen: Gesamtdistanz, Ø Pace, längster Lauf, etc.",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50}},
            },
        ),
        types.Tool(
            name="debug_raw_activities",
            description="DEBUG: Gibt die rohe API-Antwort von Nike zurück, um die Datenstruktur zu inspizieren.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


async def _dispatch(name: str, arguments: dict) -> list[types.TextContent]:
    if   name == "get_recent_runs":      return await tool_recent_runs(arguments)
    elif name == "get_run_detail":       return await tool_run_detail(arguments)
    elif name == "get_running_stats":    return await tool_stats(arguments)
    elif name == "debug_raw_activities": return await tool_debug(arguments)
    else: return [types.TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        return await _dispatch(name, arguments)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.info("401 erhalten – Token wird erneuert und Anfrage wiederholt…")
            _invalidate_token()
            try:
                return await _dispatch(name, arguments)
            except httpx.HTTPStatusError as e2:
                if e2.response.status_code == 401:
                    return [types.TextContent(type="text", text=(
                        "❌ Token-Refresh fehlgeschlagen (weiterhin 401).\n\n"
                        "Bitte NIKE_EMAIL + NIKE_PASSWORD in der Konfiguration prüfen, "
                        "oder NRC_TOKEN manuell erneuern."
                    ))]
                return [types.TextContent(type="text", text=f"API Fehler {e2.response.status_code}: {e2}")]
        return [types.TextContent(type="text", text=f"API Fehler {e.response.status_code}: {e}")]
    except (ValueError, RuntimeError) as e:
        return [types.TextContent(type="text", text=f"Fehler: {e}")]
    except Exception as e:
        logger.exception("Fehler in Tool %s", name)
        return [types.TextContent(type="text", text=f"Fehler: {type(e).__name__}: {e}")]


# ── Tool Implementierungen ─────────────────────────────────────────────────────

async def tool_recent_runs(args: dict) -> list[types.TextContent]:
    limit = min(int(args.get("limit", 10)), 50)
    raw   = await api_get_activities(limit=limit, activity_type=args.get("activity_type", "run"))
    runs  = [parse_activity(a) for a in raw]
    if not runs:
        return [types.TextContent(type="text", text="Keine Läufe gefunden.")]

    lines = [f"🏃 **Letzte {len(runs)} Läufe**\n"]
    for i, r in enumerate(runs, 1):
        date = (r["start_time"] or "")[:10]
        lines.append(
            f"**{i}. {r['name']}** ({date})\n"
            f"   📍 {r['distance_km']} km | ⏱ {r['duration']} | 🏃 {r['pace']}\n"
            f"   ❤️ {r['avg_heart_rate']} bpm | 🔥 {r['calories_kcal']} kcal | ⛰ +{r['elevation_gain_m']}m\n"
            f"   ID: `{r['activity_id']}`\n"
        )
    return [types.TextContent(type="text", text="\n".join(lines))]


async def tool_run_detail(args: dict) -> list[types.TextContent]:
    aid = args.get("activity_id", "").strip()
    if not aid:
        return [types.TextContent(type="text", text="Fehler: activity_id fehlt.")]
    data = await api_get_detail(aid)
    r    = parse_activity(data)

    hr_vals = []
    for m in data.get("metrics", []):
        if isinstance(m, dict) and m.get("type") == "heart_rate":
            hr_vals = [v.get("value") for v in m.get("values", []) if isinstance(v, dict) and v.get("value")]
    hr_line = f"\n   ❤️ Verlauf: {min(hr_vals):.0f} / {sum(hr_vals)/len(hr_vals):.0f} / {max(hr_vals):.0f} bpm (min/Ø/max)" if hr_vals else ""

    gps_count = next((len(m.get("values", [])) for m in data.get("metrics", [])
                      if isinstance(m, dict) and m.get("type") == "latitude"), 0)

    text = (
        f"🏃 **{r['name']}** ({(r['start_time'] or '')[:10]})\n\n"
        f"📍 {r['distance_km']} km | ⏱ {r['duration']} | 🏃 {r['pace']}\n"
        f"❤️ Ø {r['avg_heart_rate']} bpm | Max {r['max_heart_rate']} bpm{hr_line}\n"
        f"🔥 {r['calories_kcal']} kcal | ⛰ +{r['elevation_gain_m']}m / -{r['elevation_loss_m']}m\n"
        f"👟 {r['steps']} Schritte | 🦵 {r['avg_cadence_spm']} spm\n"
        f"🗺 {gps_count} GPS-Punkte\n"
        f"🆔 {r['activity_id']}"
    )
    return [types.TextContent(type="text", text=text)]


async def tool_stats(args: dict) -> list[types.TextContent]:
    limit = min(int(args.get("limit", 20)), 50)
    raw   = await api_get_activities(limit=limit, activity_type="run,jogging")
    runs  = [parse_activity(a) for a in raw]
    if not runs:
        return [types.TextContent(type="text", text="Keine Läufe gefunden.")]

    total_km   = sum(r["distance_km"] or 0 for r in runs)
    total_ms   = sum(r["duration_ms"] or 0 for r in runs)
    total_cal  = sum(r["calories_kcal"] or 0 for r in runs)
    total_elev = sum(r["elevation_gain_m"] or 0 for r in runs)
    dists      = [r["distance_km"] for r in runs if r["distance_km"]]
    avg_dist   = sum(dists) / len(dists) if dists else 0

    total_km_nz = sum(r["distance_km"] for r in runs if r["distance_km"] and r["duration_ms"])
    total_ms_nz = sum(r["duration_ms"] for r in runs if r["distance_km"] and r["duration_ms"])
    avg_pace = fmt_pace((total_ms_nz / 1000 / 60) / total_km_nz) if total_km_nz else "—"

    hr_vals = [r["avg_heart_rate"] for r in runs if r["avg_heart_rate"]]
    avg_hr  = round(sum(hr_vals) / len(hr_vals)) if hr_vals else "—"

    text = (
        f"📊 **Statistiken** (letzte {len(runs)} Läufe)\n\n"
        f"📍 Gesamt: {total_km:.1f} km\n"
        f"⏱ Gesamtzeit: {fmt_duration(total_ms)}\n"
        f"🔥 Kalorien: {total_cal:.0f} kcal\n"
        f"⛰ Höhenmeter: {total_elev:.0f} m\n\n"
        f"📍 Ø Distanz: {avg_dist:.2f} km\n"
        f"🏃 Ø Pace: {avg_pace}\n"
        f"❤️ Ø Herzrate: {avg_hr} bpm\n\n"
        f"🏆 Längster Lauf: {max(dists):.2f} km\n"
        f"📅 Zeitraum: {(runs[-1]['start_time'] or '')[:10]} – {(runs[0]['start_time'] or '')[:10]}"
    )
    return [types.TextContent(type="text", text=text)]


async def tool_debug(args: dict) -> list[types.TextContent]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(ACTIVITIES_URL, headers=await get_headers(),
                             params={"limit": 2, "types": "run", "include_deleted": "false"})
        try:
            data       = r.json()
            activities = data.get("activities", []) if isinstance(data, dict) else data
            preview    = json.dumps(activities[0] if activities else data, indent=2)[:3000]
            return [types.TextContent(type="text", text=f"Status: {r.status_code}\n\nStruktur:\n{preview}")]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Status: {r.status_code}\nFehler: {e}\nRaw:\n{r.text[:2000]}")]


async def main():
    logger.info("Nike Run Club MCP Server startet…")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
