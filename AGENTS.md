# AGENTS.md

Detta är ett **Home Assistant config-as-code-repo** (mest YAML) plus verktyg/dokumentation.
Det bygger/startar ingen egen tjänst lokalt — det konfigurerar en **extern, redan körande
Home Assistant-instans** och kopplar Cursor till den via **MCP**. Se `README.md` och `docs/`.

## Cursor Cloud specific instructions

### Anslutning till Home Assistant

- En **Cloud Agent kan INTE nå `192.168.x.x`** (hemnätet) och läser **inte** lokal
  `.cursor/mcp.json`. Endast **publika URL:er** fungerar, dvs Nabu Casa-URL:en. Bakgrund:
  `docs/ha-mcp.md` § 5b och `docs/cursor-cloud-mcp-steg.md`.
- HA nås utifrån via Nabu Casa-remote-URL:en (finns i `configuration.yaml` → `external_url`).
  REST API fungerar därifrån med en long-lived token:
  `curl -H "Authorization: Bearer <token>" <nabu-url>/api/` → `200 {"message":"API running."}`.
- **Hemligheten i denna miljö är ovanligt lagrad:** secret-*namnet* är HA:s Nabu-Casa-URL och
  secret-*värdet* är en long-lived token (JWT). `scripts/verify-ha-mcp.sh` hittar den automatiskt.
  Skriv aldrig ut token-värdet i loggar/artefakter.

### Verifiera anslutningen (Linux/Cloud)

- `bash scripts/verify-ha-mcp.sh` — kontrollerar REST API (401 utan auth, 200 med token) och,
  om `HA_MCP_WEBHOOK_URL` eller `.cursor/mcp.json` finns, MCP-webhooken (förväntat 405).
  Detta är Linux-motsvarigheten till `scripts/verify-ha-mcp.ps1` (PowerShell, för Windows).
- `bash scripts/ha-inventory.sh` kräver `.env` med `HA_URL` + `HA_TOKEN` (se `scripts/lib/ha_api.sh`).

### MCP-servern (det som faktiskt "kopplar" Cursor till HA)

- HA:s enda MCP-server här är **ha-mcp-add-on:et exponerat via Nabu Casa-webhook**
  (`<nabu-url>/api/webhook/mcp_<hemlighet>`). Den **inbyggda** `mcp_server`-integrationen är
  **inte installerad** (`/mcp_server/sse` → 404).
- För att en **Cloud Agent / Cursor Automation** ska kunna använda MCP måste servern
  `home-assistant` läggas till i **cursor.com → Settings → MCP** med webhook-URL:en
  (kopieras från HA:s proxy-add-on-logg). Detta går **inte** att göra från repot eller via en
  env-hemlighet — det är en dashboard-åtgärd. Steg: `docs/cursor-cloud-mcp-steg.md`.
- Webhook-URL:en är en hemlighet (bred HA-admin). Committa den aldrig; `.cursor/mcp.json` är
  gitignorerad.

### Säkerhet

- Följ `.cursor/rules/ha-projekt.mdc`: committa aldrig token/lösenord/`secrets.yaml`/`.env`.
  `scripts/pre-commit-check.sh` blockerar vanliga misstag.
