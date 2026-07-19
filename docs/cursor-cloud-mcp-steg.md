# Cursor Cloud MCP — engångssteg för Automations

Datum: 2026-07-19

**Varför:** Cursor Automations (t.ex. `cursor+ha test`) och Cloud Agents kör i Cursors moln. De läser **inte** din lokala `~/.cursor/mcp.json` eller projektets `.cursor/mcp.json`. Du måste lägga till Home Assistant MCP i **cursor.com-dashboarden**.

Lokal Agent-chatt på din dator fungerar redan om `mcp.json` är korrekt. Detta steg behövs bara för **molnbaserade** körningar.

## 1. Öppna rätt sida (inte Secrets)

Gå till **[https://cursor.com/agents](https://cursor.com/agents)** och logga in.

> **Föråldrat:** `cursor.com/settings/mcp` finns inte längre som MCP-inställningssida.
>
> **Fel ställe:** *Add Secrets* under Cloud Agents — det är för REST-token/miljövariabler, **inte** MCP.

Team-admins kan alternativt lägga till delad MCP under **[cursor.com/dashboard/integrations](https://cursor.com/dashboard/integrations)** → **Add MCP**.

## 2. Lägg till ny MCP-server

På agents-sidan: öppna **MCP**-menyn (dropdown/knapp nära agentfältet) → **Add MCP** / **Add custom MCP**.

| Fält | Värde |
|------|-------|
| **Namn** | `home-assistant` |
| **Typ** | HTTP (streamable HTTP) |
| **Server URL** | Din Nabu Casa-webhook (se nedan) |

**Viktigt:** Servernamnet måste vara exakt `home-assistant` — samma som i din lokala `mcp.json`. Automationen matchar mot detta namn, inte `user-home-assistant` eller liknande.

## 3. Kopiera webhook-URL från Home Assistant

1. HA → **Inställningar → Tillägg → Nabu Casa – Webhook Proxy for HA MCP**
2. Öppna **Logg**
3. Kopiera raden `MCP Server URL (remote):`

Format:

```
https://<din-nabu>.ui.nabu.casa/api/webhook/mcp_<hemlighet>
```

### JSON-mall (klistra in URL:en från HA-loggen)

Om dashboarden ber om JSON:

```json
{
  "mcpServers": {
    "home-assistant": {
      "url": "https://85gdgmd5j5v1zlxo4dmkybhmvol6ozqk.ui.nabu.casa/api/webhook/mcp_BYT_UT_MOT_HEMLIGHET_FRAN_HA_LOGG"
    }
  }
}
```

> **Säkerhet:** Webhook-URL:en är en hemlighet — den ger bred HA-administration. Committa den aldrig till git. Mallen ovan maskerar hemligheten med `BYT_UT_…`.

Hämta den riktiga URL:en från din lokala fil (visas maskerad):

```powershell
(Get-Content "$env:USERPROFILE\.cursor\mcp.json" | ConvertFrom-Json).mcpServers.'home-assistant'.url -replace '/mcp_[a-f0-9]+$', '/mcp_****'
```

## 4. Spara och verifiera

1. Spara MCP-servern i dashboarden
2. Kontrollera att den visas som ansluten (inte röd/fel)
3. Kör lokalt: `.\scripts\verify-ha-mcp.ps1` — alla kontroller ska vara OK

## 5. Kontrollera automationen `cursor+ha test`

1. Öppna automationen i Cursor (Automations-vyn)
2. Under **Tools** / **MCP**: välj **home-assistant**
3. Om raden står i **"Set up MCP"** har cloud MCP inte lagts till eller namnet matchar inte
4. Kör automationen igen

Automationen lagras i Cursor-molnet — den finns inte i detta git-repo.

## Snabbreferens

| Miljö | Läser lokal mcp.json? | Kräver cursor.com MCP? |
|-------|----------------------|------------------------|
| Lokal Agent-chatt | Ja | Nej |
| Cloud Agent | Nej | Ja |
| Cursor Automation | Nej | Ja |

Se även [ha-mcp.md § 5b](ha-mcp.md#5b-felsökning--cursor-automation--agenten-cursorha-test-når-inte-ha).
