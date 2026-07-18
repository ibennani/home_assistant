# Home Assistant MCP — lägesbild och Cursor-koppling

Datum: 2026-07-19  
Källor: `reports/inventory-*.json`, HA REST API, [homeassistant-ai/ha-mcp](https://github.com/homeassistant-ai/ha-mcp)

## Vad som redan är installerat

Inventering (`reports/inventory-20260719T005637Z.json`) och live API-kontroll visar följande MCP-relaterade komponenter:

| Del | Status | Version / detalj |
|-----|--------|------------------|
| **HA-MCP Custom Component** (`ha_mcp_tools`) | Installerad, laddad | v7.13.0 |
| Config entry: **HA-MCP File & YAML Tools** | Aktiv | Privilegierade fil-/YAML-tjänster för ha-mcp |
| Config entry: **HA-MCP Server** (in-process) | **Saknas** | Endast File & YAML Tools är tillagd |
| **Home Assistant MCP Server** (add-on) | Installerad | v7.13.0 — port **9583** svarar (403 utan hemlig sökväg = servern kör) |
| **Nabu Casa – Webhook Proxy for HA MCP** (add-on) | Installerad | v2.0.3 |
| **MCP Webhook Proxy** (`mcp_proxy` integration) | Installerad, laddad | Proxar webhook → MCP-servern |

### Vad som *inte* syns i YAML-repot

`configuration.yaml`, `automations.yaml` och `scripts.yaml` innehåller **inga** MCP-referenser. Allt är installerat via HACS / add-on-butiken / UI (config entries), inte via versionshanterad YAML.

### `.env` och API

- `HA_TOKEN` är satt (183 tecken) — används av `scripts/ha-inventory.ps1`
- `HA_URL`: `http://192.168.0.222:8123`
- Supervisor API (`/api/hassio/addons`) returnerar 401 med nuvarande token — add-on-status måste läsas i HA UI eller via SSH

## Vad gör `ha_mcp_tools`?

[HA-MCP Custom Component](https://github.com/homeassistant-ai/ha-mcp-integration) (`ha_mcp_tools`) är **en** integration med **två oberoende config entries**:

1. **HA-MCP Server** — kör hela ha-mcp-servern *in-process* i Home Assistant (rekommenderat för Container/Core; fungerar även på HA OS). Exponerar webhook-URL för fjärråtkomst via Nabu Casa utan separat proxy.
2. **HA-MCP File & YAML Tools** — privilegierade HA-tjänster för filsystem och säker YAML-redigering. Krävs bara om ha-mcp:s opt-in fil-/YAML-verktyg ska användas.

**Din installation har entry (2) men inte (1).** Själva MCP-servern körs i stället via **add-on** (se nedan).

### Relaterade add-ons

| Add-on | Roll |
|--------|------|
| **Home Assistant MCP Server** | Kör ha-mcp som add-on (lokal port 9583, hemlig sökväg). Har inbyggd "Connection Guide" / Web UI med klipp-och-klistra-konfig för Cursor m.fl. |
| **Nabu Casa – Webhook Proxy for HA MCP** | Installerar/uppdaterar `mcp_proxy`-integrationen och skapar en **webhook-URL** (`/api/webhook/mcp_…`) som proxar till MCP-servern. Gör att Cursor kan nå HA utifrån via Nabu Casa utan port forwarding. |

`mcp_proxy` kör **inte** en egen MCP-server — den vidarebefordrar bara trafik till add-on-servern.

## Cursor MCP vs HA-intern MCP

| | **Cursor MCP** (detta repo / utveckling) | **HA-intern MCP** (Assist / röst / chatt i HA) |
|---|------------------------------------------|------------------------------------------------|
| **Syfte** | Låta Cursor (eller Claude Desktop m.fl.) styra och konfigurera HA via AI | Låta HA:s egna conversation-agenter använda ha-mcp-verktyg |
| **Klient** | Extern MCP-klient (Cursor) | OpenAI Conversation, inbyggd Assist, voice satellites |
| **Anslutning** | HTTP-URL i `.cursor/mcp.json` (lokal port eller Nabu Casa-webhook) | LLM API "HA-MCP Server (tool search)" i agentens inställningar |
| **Token** | Webhook-URL *är* hemligheten; lokal direkt-URL kräver hemlig sökväg från add-on | Loopback inuti HA — inget externt MCP-token |

De kompletterar varandra: Cursor för utveckling och felsökning i detta repo; HA-intern MCP för "prata med huset" via Assist.

## Kan MCP ersätta WhatsApp-målet?

**Nej, inte direkt.** De löser olika problem:

| Mål | Lösning |
|-----|---------|
| **WhatsApp-chatt med Assist** | WhatsApp-brygga + automation (`conversation.process`) — se [whatsapp-chatt-plan.md](whatsapp-chatt-plan.md) |
| **AI i Cursor som kan läsa/skriva HA** | ha-mcp + Cursor MCP (detta dokument) |

WhatsApp saknas fortfarande som integration (`whatsapp` finns inte bland komponenter). MCP hjälper dig att *bygga och underhålla* automationer snabbare i Cursor, men ersätter inte WhatsApp-kanalen.

**Indirekt koppling:** Om du aktiverar **HA-MCP Server** (in-process eller add-on) och kopplar den till en conversation-agent som LLM API kan samma verktyg användas från Assist-chatt — men WhatsApp-flödet behöver fortfarande en WhatsApp-integration och automation som anropar `conversation.process`.

## Praktiska nästa steg: koppla Cursor

### 1. Hämta anslutnings-URL

**Alternativ A — Lokal nätverksåtkomst (enklast hemma):**

1. HA → **Inställningar → Tillägg → Home Assistant MCP Server**
2. Öppna **OPEN WEB UI** / Connection Guide
3. Kopiera URL för Cursor (format ungefär `http://192.168.0.222:9583/private_<hemlighet>`)

Verifierat: port **9583** på `192.168.0.222` svarar (403 utan rätt sökväg = servern kör).

**Alternativ B — Fjärråtkomst via Nabu Casa (Cursor utanför hemnätet):**

1. HA → **Inställningar → Tillägg → Nabu Casa – Webhook Proxy for HA MCP**
2. Läs add-on-loggen efter raden `MCP Server URL (remote):`
3. URL-format: `https://<din-nabu-casa>.ui.nabu.casa/api/webhook/mcp_<hemlighet>`

Behandla webhook-URL:en som ett lösenord — den ger bred HA-administration via MCP.

### 2. Skapa projektets MCP-konfiguration

Skapa `C:\kod\home_assistant\.cursor\mcp.json`:

```json
{
  "mcpServers": {
    "home-assistant": {
      "url": "http://192.168.0.222:9583/private_BYT_UT"
    }
  }
}
```

För Nabu Casa-webhook, byt `url` till den fjärr-URL du kopierade från proxy-add-onens logg.

**Tips:** Lägg inte `HA_TOKEN` i denna fil om du använder webhook-URL — hemligheten ligger i URL:en. För stdio/pip-installation (ej ditt nuvarande upplägg) behövs token via miljövariabler.

### 3. Starta om Cursor

Stäng och öppna Cursor (eller *Developer: Reload Window*). Kontrollera **Settings → MCP** — servern ska visa *Connected*.

### 4. Kända problem (Cursor + ha-mcp v7.x)

Cursor har haft buggar med MCP-ikonvalidering mot nyare ha-mcp-versioner ([issue #375](https://github.com/homeassistant-ai/ha-mcp/issues/375)). Om anslutningen misslyckas:

- Uppdatera Cursor till senaste versionen
- Testa webhook-URL i stället för direkt port
- Som sista utväg: äldre ha-mcp-version utan ikoner (se FAQ i ha-mcp-repot)

### 5. Valfritt — förenkla stacken

Du kör idag **add-on + webhook-proxy + File & YAML Tools**. Alternativ:

| Nuvarande | Alternativ |
|-----------|------------|
| MCP Server add-on + Webhook Proxy add-on | **HA-MCP Server** config entry (in-process) — inbyggd webhook, ingen separat proxy |
| Endast File & YAML Tools | Behåll om du vill ha YAML/fil-verktyg; annars räcker server-entry |

Ha **inte** både in-process server *och* add-on igång samtidigt om du inte vet vad du gör (olika portar, men dubbel administration).

## Snabbreferens — kommandon i detta repo

```powershell
# Uppdatera inventering (reports/ gitignorerad)
.\scripts\ha-inventory.ps1

# Lägesrapport med MCP-rad
# Se docs/lage-rapport.md
```

## Länkar

- [ha-mcp (officiellt)](https://github.com/homeassistant-ai/ha-mcp)
- [ha-mcp-integration (HACS-komponent)](https://github.com/homeassistant-ai/ha-mcp-integration)
- [In-process server-dokumentation](https://github.com/homeassistant-ai/ha-mcp/blob/master/docs/in-process-server.md)
- [Cursor MCP-dokumentation](https://cursor.com/docs/mcp)
- [WhatsApp-chattplan](whatsapp-chatt-plan.md)
