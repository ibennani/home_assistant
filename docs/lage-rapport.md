# Lägesrapport (genererad från repo + nätverkstest)

Datum: 2026-07-19

## Vad som fungerar

| Test | Resultat |
|------|----------|
| Ping `192.168.0.222` | OK |
| Ping `homeassistant.local` | OK |
| HA REST API (lokalt) | OK |
| HA REST API (Nabu Casa) | OK |
| GitHub-repo | Publikt |
| `.env` | `HA_URL` + `HA_TOKEN` konfigurerade |
| `ha-inventory.ps1` | OK — rapport i `reports/` (gitignorerad) |

## Inventering (2026-07-19, `reports/inventory-20260719T005526Z.json`)

| Punkt | Värde |
|-------|-------|
| HA-version | **2026.6.4** |
| Komponenter | **436** |
| Tidszon | Europe/Stockholm |
| WhatsApp-integration | **Saknas** (`whatsapp` finns inte bland komponenter) |
| Conversation-agenter | `conversation.home_assistant`, `conversation.openai_conversation` |
| HACS | Installerad |
| Assist Pipeline | Installerad (`assist_pipeline`) |
| HA MCP Tools | Installerad (`ha_mcp_tools`) |
| Add-ons (Supervisor API) | **Tom lista** — se notering nedan |

### Add-ons API tom

`/api/hassio/addons` returnerade inga tillägg. Troliga orsaker:

- Long-lived access token saknar Supervisor-rättighet (vanligt med standard-token från användarprofilen)
- Endpointen kräver HA OS med Supervisor; även då kan REST-token begränsas till vanliga API-anrop

Kör `ha core info` via SSH eller kontrollera i HA UI under **Inställningar → Tillägg** för faktisk add-on-lista.

## Vad som inte fungerar ännu

| Test | Resultat |
|------|----------|
| SSH `root@192.168.0.222` | Fel: `Corrupted MAC on input` (Windows OpenSSH) — använd `scripts/ssh-ha.ps1` |
| WhatsApp-chatt | Ingen WhatsApp-integration installerad |

## Din installation (från `configuration.yaml` + API)

- **HA OS** med Nabu Casa (`cloud:` aktiverat), Supervisor-komponenter (`hassio`, `hassio.*`)
- **Intern URL:** `http://192.168.0.222:8123`
- **Extern URL:** Nabu Casa (i `configuration.yaml`)
- **Notiser:** `mobile_app` (flera telefoner), `joaoapps_join` (Join)
- **Röst/Assist:** Google Home, `google_translate` TTS, OpenAI Conversation, Assist Pipeline
- **Webhooks:** Ja (t.ex. `mobillarmet_morgon_vardagar`, `testtrigger`)
- **Automatiseringar:** Stor `automations.yaml` (~8000 rader)

## Saknas för WhatsApp-chatt

1. **WhatsApp-brygga** (add-on + integration, t.ex. FaserF/ha-whatsapp)
2. **Conversation-agent** — redan två agenter (`home_assistant`, `openai_conversation`); välj/vitlista för inkommande WhatsApp
3. **Automation** — mall finns: `automations/whatsapp_assist.yaml.example`
4. **Vitlistat telefonnummer** i `secrets.yaml`

## Rekommenderad ordning

1. ~~Sätt `HA_TOKEN` i `.env`~~ — klart
2. ~~Kör `.\scripts\ha-inventory.ps1`~~ — klart (uppdatera vid behov)
3. Installera WhatsApp-brygga (se `docs/whatsapp-chatt-plan.md`)
4. Deploya automation från `automations/whatsapp_assist.yaml.example`

## Säkerhet (viktigt — publikt repo)

`configuration.yaml` innehöll **Join API-nycklar i klartext**. Dessa har flyttats till `!secret` i en uppdatering.
**Byt/regenerera Join API-nycklar** i Join-appen om de legat publikt länge.

Gamla lösenord i kommenterade rader i yaml (netgear, spotify m.m.) finns kvar i **git-historik** — rotera om de varit riktiga.
