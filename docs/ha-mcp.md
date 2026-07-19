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
| **Home Assistant MCP Server** | Kör ha-mcp som add-on (lokal port 9583, hemlig sökväg). Web UI via ingress = verktygsinställningar (Tools/Settings); anslutnings-URL finns i **Logg** eller **Konfiguration** (se felsökning nedan). |
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
2. Öppna fliken **Logg** (eller **Konfiguration** → avancerade alternativ → `secret_path`)
3. Kopiera URL för Cursor (format ungefär `http://192.168.0.222:9583/private_<hemlighet>`)

> **Obs:** Knappen **Öppna webbgränssnitt** visar bara Tools/Settings — inte Connection Guide. Se [felsökning](#felsökning-web-ui-visar-bara-tools--settings) om du landar där.

Verifierat: port **9583** på `192.168.0.222` svarar (403 utan rätt sökväg = servern kör).

#### Felsökning: Web UI visar bara Tools / Settings

I ha-mcp v7.x öppnar **Öppna webbgränssnitt** (Supervisor ingress) **endast inställningssidan** — flikarna Tools och Settings. Det finns **ingen Connection Guide** där. Det är förväntat beteende, inte en trasig installation.

**Var hittar du URL:en i stället?**

| Plats | Vad du letar efter |
|-------|---------------------|
| **Home Assistant MCP Server → Logg** | Raden `🔐 MCP Server URL: http://192.168.0.222:9583/private_…` (vid start; scrolla om loggen är lång) |
| **Home Assistant MCP Server → Konfiguration** | Aktivera *Visa oanvända valfria konfigurationsalternativ* längst ned → fältet `secret_path` (t.ex. `/private_abc…`). Bygg URL: `http://<HA-IP>:9583` + värdet (med inledande `/`) |
| **Nabu Casa – Webhook Proxy for HA MCP → Logg** | Raden `MCP Server URL (remote): https://….ui.nabu.casa/api/webhook/mcp_…` — för Cursor utanför hemnätet |

**Bygg lokal URL manuellt:**

```
http://192.168.0.222:9583/private_<din-hemlighet>
```

- Porten är **9583** (fast i add-on).
- Hemligheten genereras automatiskt vid första start och sparas i add-on-containern som `/data/secret_path.txt` (kräver Terminal/SSH-add-on om du vill läsa filen direkt).
- `secret_path` i Konfiguration är samma värde som i loggen — om fältet är tomt har add-on genererat en automatiskt (syns bara i logg/fil, inte i Web UI).

**Testa att sökvägen stämmer:** `curl http://192.168.0.222:9583/` → **403** (servern kör, fel sökväg). Med rätt `private_…`-sökväg får du **405** på GET (MCP-endpointen svarar — det är OK).

**Alternativ B — Fjärråtkomst via Nabu Casa (Cursor utanför hemnätet):**

1. HA → **Inställningar → Tillägg → Nabu Casa – Webhook Proxy for HA MCP**
2. Läs add-on-loggen efter raden `MCP Server URL (remote):`
3. URL-format: `https://<din-nabu-casa>.ui.nabu.casa/api/webhook/mcp_<hemlighet>`

Behandla webhook-URL:en som ett lösenord — den ger bred HA-administration via MCP.

### 2. Skapa MCP-konfiguration

Cursor läser **två** `mcp.json`-filer och slår ihop dem:

| Plats | Sökväg | Syfte |
|-------|--------|--------|
| **Projekt** | `C:\kod\home_assistant\.cursor\mcp.json` | Team-/projektspecifik (gitignorerad — innehåller hemlig URL) |
| **Global** | `C:\Users\iliben\.cursor\mcp.json` | Personlig, alla projekt |

Om samma servernamn finns i båda vinner projektfilen.

**Viktigt om Settings → Tools & MCP:** Cursor visar i praktiken bara servrar från den **globala** filen (`~/.cursor/mcp.json`) i inställnings-UI:t. En server som bara finns i projektets `.cursor/mcp.json` kan fungera i Agent-chatt men **syns inte** under Tools & MCP. Lägg därför till `home-assistant` i den globala filen om du vill se och växla den där.

#### Projekt (valfritt, för dokumentation i repot)

Kopiera `.cursor/mcp.json.example` till `.cursor/mcp.json` (filen är gitignorerad).

**Rekommenderat:** Nabu Casa-webhook (fungerar hemma, utanför LAN, och krävs för Cloud Agents / Automations):

```json
{
  "mcpServers": {
    "home-assistant": {
      "url": "https://<din-nabu>.ui.nabu.casa/api/webhook/mcp_<hemlighet>"
    }
  }
}
```

**Alternativ hemma i LAN:** lokal add-on-URL från **Logg** (fungerar **inte** från Cloud Agent / Automation):

```json
{
  "mcpServers": {
    "home-assistant": {
      "url": "http://192.168.0.222:9583/private_<hemlighet>"
    }
  }
}
```

#### Global (rekommenderat för att synas i Settings)

Lägg till samma post i `C:\Users\iliben\.cursor\mcp.json` under befintliga `mcpServers`:

```json
"home-assistant": {
  "url": "http://192.168.0.222:9583/private_<din-hemlighet>"
}
```

För Nabu Casa-webhook, byt `url` till den fjärr-URL du kopierade från proxy-add-onens logg.

**Format:** ha-mcp v7.x (add-on) är en HTTP/streamable MCP-server. Cursor behöver bara fältet `"url"` — **inte** `"command"`, `"args"` eller `"type": "streamableHttp"`. (Claude Desktop behöver däremot `uvx mcp-proxy` — det gäller inte Cursor.)

**Tips:** Lägg inte `HA_TOKEN` i denna fil om du använder webhook-URL — hemligheten ligger i URL:en. För stdio/pip-installation (ej ditt nuvarande upplägg) behövs token via miljövariabler.

### 3. Starta om Cursor

Stäng och öppna Cursor (eller *Developer: Reload Window*). Kontrollera **Settings → Tools & MCP** — `home-assistant` ska synas om den ligger i den globala `mcp.json`.

### 4. Verifiera anslutning

**Nätverk (PowerShell):**

```powershell
# 403 = servern kör, fel sökväg
Invoke-WebRequest -Uri "http://192.168.0.222:9583/" -UseBasicParsing
# 405 på GET med rätt private_-sökväg = MCP-endpoint svarar (förväntat)
Invoke-WebRequest -Uri "http://192.168.0.222:9583/private_<hemlighet>" -UseBasicParsing
```

Verifierat 2026-07-19: `192.168.0.222:9583` svarar (403 utan sökväg, 405 med korrekt `private_…`).

**MCP-loggar:** Output-panelen (Ctrl+Shift+U) → välj **MCP Logs** i listan. Leta efter `home-assistant` och eventuella anslutningsfel.

### 5. Felsökning — servern syns inte i Tools & MCP

| Symptom | Trolig orsak | Åtgärd |
|---------|--------------|--------|
| Ingen `home-assistant` i Settings | Endast projekt-`.cursor/mcp.json` skapad | Lägg till servern i `C:\Users\iliben\.cursor\mcp.json` (se ovan) |
| Fortfarande ingen server | Fel workspace-mapp öppnad | Öppna mappen `C:\kod\home_assistant` som rot (inte en undermapp) |
| Server listad men röd / Error | Cursor + ha-mcp ikon-bugg | Uppdatera Cursor; se avsnitt 6 nedan |
| JSON läses inte | Syntaxfel i `mcp.json` | Validera med `Get-Content .cursor\mcp.json \| ConvertFrom-Json` |
| Timeout / nätverksfel | Inte på samma nät som HA | Testa URL i webbläsare eller PowerShell; använd Nabu Casa-webhook utanför LAN |

### 5b. Felsökning — Cursor Automation / agenten "cursor+ha test" når inte HA

**Symptom:** En **Cursor Automation** (t.ex. `cursor+ha test`) eller **Cloud Agent** kan inte använda Home Assistant, medan vanlig Agent-chatt i Cursor på din dator fungerar.

**Diagnos (verifierat 2026-07-19):**

| Kontroll | Resultat | Betydelse |
|----------|----------|-----------|
| `http://192.168.0.222:9583/` | **403** | MCP add-on kör |
| `http://192.168.0.222:9583/private_…` | **405** | Lokal MCP-endpoint svarar |
| Nabu Casa-webhook (`…/api/webhook/mcp_…`) | **405** | Fjärr-URL fungerar (rätt hemlighet) |
| `http://192.168.0.222:8123/api/` med `HA_TOKEN` | **200** | HA REST API OK |
| Agent-chatt lokalt (`ha_get_overview`) | OK | `mcp.json` är korrekt konfigurerad |

**Rotorsak:** Cursor läser `mcp.json` **bara på din dator** (lokal Agent-chatt). **Cursor Automations** och **Cloud Agents** kör i Cursors moln och har **inte** åtkomst till din lokala `~/.cursor/mcp.json` eller projektets `.cursor/mcp.json`. De kan heller inte nå `192.168.x.x` — endast publika URL:er (t.ex. Nabu Casa-webhook).

| Körningsläge | Läser lokal `mcp.json`? | Når `192.168.x.x`? | Når Nabu-webhook? |
|--------------|-------------------------|--------------------|--------------------|
| **Lokal Agent-chatt** (Cursor på din PC) | Ja | Ja (hemma) | Ja |
| **Cloud Agent** | Nej | Nej | Ja (om MCP lagts till i dashboard) |
| **Cursor Automation** (`cursor+ha test` m.fl.) | Nej | Nej | Ja (om MCP lagts till i dashboard) |

**Åtgärd för Automations / Cloud Agent:**

Steg-för-steg med JSON-mall: **[docs/cursor-cloud-mcp-steg.md](cursor-cloud-mcp-steg.md)**

1. Gå till **[cursor.com/agents](https://cursor.com/agents)** (MCP-menyn nära agentfältet — **inte** Add Secrets, **inte** `cursor.com/settings/mcp`)
2. Lägg till en **ny MCP-server** med namnet `home-assistant` (exakt stavning — automationen matchar `serverName`, inte `user-home-assistant`)
3. Använd **Nabu Casa-webhook-URL** (inte `192.168.x.x`):
   - HA → **Tillägg → Nabu Casa – Webhook Proxy for HA MCP → Logg**
   - Kopiera raden `MCP Server URL (remote): https://….ui.nabu.casa/api/webhook/mcp_…`
4. Spara och öppna automationen `cursor+ha test` → kontrollera att verktyget **home-assistant** är valt och inte står i "Set up MCP"
5. Kör automationen igen

**Snabbtest lokalt:** `.\scripts\verify-ha-mcp.ps1` (LAN 403, webhook 405, REST API 200, mcp.json-matchning)

**Åtgärd om du bara vill köra lokalt:** Använd **lokal Agent-chatt** (inte Cloud/Automation), eller ställ in automationen till **local runtime** om det finns som alternativ.

**Vanliga misstag:**

| Misstag | Varför det strular |
|---------|-------------------|
| Bara `mcp.json` på datorn | Automations/Cloud ser inte filen |
| Lokal URL (`192.168.0.222:9583/…`) i automation | Molnet når inte hemnätet |
| MCP-servern heter något annat i automationen | Måste matcha `serverName` i dashboard (t.ex. `home-assistant`) |
| Webhook-URL roterad i HA men inte uppdaterad i Cursor | Kopiera ny URL från proxy-add-onens logg |

**Snabbtest (PowerShell, på din dator):**

```powershell
.\scripts\verify-ha-mcp.ps1
```

Manuellt (samma förväntade svar):

```powershell
# 403 = add-on kör
curl.exe -s -o NUL -w "%{http_code}" http://192.168.0.222:9583/

# 405 = webhook-URL giltig (byt ut … mot din maskerade URL)
curl.exe -s -o NUL -w "%{http_code}" "https://….ui.nabu.casa/api/webhook/mcp_…"
```

### 6. Kända problem (Cursor + ha-mcp v7.x)

Cursor har haft buggar med MCP-ikonvalidering mot nyare ha-mcp-versioner ([issue #375](https://github.com/homeassistant-ai/ha-mcp/issues/375)). Om anslutningen misslyckas:

- Uppdatera Cursor till senaste versionen
- Testa webhook-URL i stället för direkt port
- Som sista utväg: äldre ha-mcp-version utan ikoner (se FAQ i ha-mcp-repot)

### 7. Valfritt — förenkla stacken

Du kör idag **add-on + webhook-proxy + File & YAML Tools**. Alternativ:

| Nuvarande | Alternativ |
|-----------|------------|
| MCP Server add-on + Webhook Proxy add-on | **HA-MCP Server** config entry (in-process) — inbyggd webhook, ingen separat proxy |
| Endast File & YAML Tools | Behåll om du vill ha YAML/fil-verktyg; annars räcker server-entry |

Ha **inte** både in-process server *och* add-on igång samtidigt om du inte vet vad du gör (olika portar, men dubbel administration).

## Snabbreferens — kommandon i detta repo

```powershell
# Verifiera MCP (LAN + Nabu webhook + REST API + mcp.json)
.\scripts\verify-ha-mcp.ps1

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
