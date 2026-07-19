# AGENTS.md

Detta repo versionerar Home Assistant-konfiguration och dokumentation. Det kör ingen egen HA-instans — Cursor kopplas till den via MCP och REST.

## Cursor Cloud — kort

| Vad | Hur | Fungerar i Cloud? |
|-----|-----|-------------------|
| REST API + Assist | Hemlighet: **namn** = Nabu Casa-URL, **värde** = long-lived token | Ja (redan OK hos dig) |
| MCP (`home-assistant`) | HTTP-server med **webhook-URL** i Cursor-dashboard | **Nej förrän du lagt till den** |

Cloud Agent kan **inte** nå `192.168.x.x` och läser **inte** lokal `~/.cursor/mcp.json` eller projektets `.cursor/mcp.json`.

### MCP i Cloud (det som saknas)

1. Öppna **[cursor.com/agents](https://cursor.com/agents)** (inte Secrets, inte `cursor.com/settings/mcp`).
2. MCP-menyn nära agentfältet → **Add MCP** → typ **HTTP**.
3. **Name:** `home-assistant`
4. **Server URL:** Nabu Casa-webhook från HA → Tillägg → *Nabu Casa – Webhook Proxy for HA MCP* → Logg → `MCP Server URL (remote):`

Webhook-URL:en är en hemlighet — committa den aldrig. Lokal kopia: `~/.cursor/mcp.json` (gitignorerad).

Team-admins kan alternativt lägga till delad MCP under [cursor.com/dashboard/integrations](https://cursor.com/dashboard/integrations).

Steg-för-steg: [docs/cursor-cloud-mcp-steg.md](docs/cursor-cloud-mcp-steg.md). Bakgrund: [docs/ha-mcp.md](docs/ha-mcp.md) § 5b.

### Verifiera

- Windows: `.\scripts\verify-ha-mcp.ps1`
- Linux/Cloud: `bash scripts/verify-ha-mcp.sh`

### Säkerhet

Följ `.cursor/rules/ha-projekt.mdc`: committa aldrig token, `secrets.yaml`, `.env` eller webhook-URL.
