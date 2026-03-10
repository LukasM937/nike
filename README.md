# Nike Run Club MCP Server 🏃

A Model Context Protocol (MCP) server for Python that fetches Nike Run Club training data via the unofficial NRC API — usable directly in Claude Desktop.

> **Note:** Nike does not provide an official public API. This server uses the same endpoints that the Nike website uses internally. These endpoints may change at any time without notice.

---

## Requirements

- Python 3.10+
- A Nike account with training data in Nike Run Club
- Claude Desktop

---

## Installation

```bash
pip install mcp httpx
```

---

## Getting Your Bearer Token

1. Go to **https://www.nike.com/member/profile** and **log out**
2. Open **Browser DevTools** (F12) → **Network** tab
3. **Log in**
4. Filter requests to `api.nike.com`
5. Click any request → **Headers** → copy the value after `Authorization: Bearer `

⚠️ Enter the token **without** the `Bearer ` prefix in the config!  
⚠️ Tokens expire after a few hours — just repeat the steps above when you get a `401` error.

---

## Claude Desktop Setup

Open the config file:

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Add the following (use absolute paths!):

```json
{
  "mcpServers": {
    "nike-run-club": {
      "command": "/absolute/path/to/python",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "NRC_TOKEN": "your_bearer_token_here"
      }
    }
  }
}
```

**Conda users:**
```json
"command": "/Users/YOUR_USER/miniforge3/envs/mcp/bin/python"
```

Restart Claude Desktop afterwards.

---

## Available Tools

| Tool | Description |
|------|-------------|
| `get_recent_runs` | Fetch recent runs with distance, pace, heart rate, calories, elevation |
| `get_run_detail` | Detailed data for a single run incl. GPS points & heart rate progression |
| `get_running_stats` | Aggregated stats: total distance, avg pace, longest run, etc. |
| `debug_raw_activities` | Raw API response for debugging |

---

## Example Prompts in Claude

- "Show me my last 5 runs"
- "What was my average pace this month?"
- "Show me the heart rate data from my last run"
- "How many kilometers have I run in the last 20 runs?"
- "Compare my last 3 runs"

---

## API Endpoints (as of 2025)

| Purpose | Endpoint |
|---------|---------|
| Activity list | `GET /plus/v3/activities/before_id/v3/*` |
| Pagination | `GET /plus/v3/activities/before_id/v3/{before_id}` |
| Activity details | `GET /sport/v3/me/activity/{id}?metrics=ALL` |

---

## Known Limitations

- No official API support from Nike
- Bearer token expires regularly (every few hours)
- Nike can change API endpoints at any time

---

## Credits & References

- [dailydataapps.com – NRC Python Export](https://dailydataapps.com/exporting-nike-run-club-data-with-python/)
- [nrc-exporter by yasoob](https://github.com/yasoob/nrc-exporter)
- [NikePlus API Gist by niw](https://gist.github.com/niw/858c1ecaef89858893681e46db63db66)
- [node-nikerunclub by jzarca01](https://github.com/jzarca01/node-nikerunclub)

---

## AI Usage

This code was generated with Claude Sonnet 4.6
And therefore can be considered AI-Generated-Code.

## License

MIT