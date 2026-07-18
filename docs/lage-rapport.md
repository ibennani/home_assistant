# Lägesrapport (genererad från repo + nätverkstest)

Datum: 2026-07-19

## Vad som fungerar

| Test | Resultat |
|------|----------|
| Ping `192.168.0.222` | OK |
| Ping `homeassistant.local` | OK |
| HA REST API (lokalt) | OK (401 utan token = servern svarar) |
| HA REST API (Nabu Casa) | OK (401 utan token) |
| GitHub-repo | Publikt |
| `.env` | Skapad med URL:er — **HA_TOKEN saknas** |

## Vad som inte fungerar ännu

| Test | Resultat |
|------|----------|
| SSH `root@192.168.0.222` | Fel: `Corrupted MAC on input` (Windows OpenSSH) |
| `ha-inventory.ps1` | Kräver `HA_TOKEN` i `.env` |
| WhatsApp-chatt | Ingen WhatsApp-integration i config |

## Din installation (från `configuration.yaml`)

- **HA OS** med Nabu Casa (`cloud:` aktiverat)
- **Intern URL:** `http://192.168.0.222:8123`
- **Extern URL:** Nabu Casa (i `configuration.yaml`)
- **Notiser:** `mobile_app` (flera telefoner), `joaoapps_join` (Join)
- **Röst:** Google Home (flera rum), `google_translate` TTS
- **Webhooks:** Ja (t.ex. `mobillarmet_morgon_vardagar`, `testtrigger`)
- **Automatiseringar:** Stor `automations.yaml` (~8000 rader)

## Saknas för WhatsApp-chatt

1. **WhatsApp-brygga** (add-on + integration, t.ex. FaserF/ha-whatsapp)
2. **Conversation-agent** (kolla i HA UI: Inställningar → Assisterare)
3. **Automation** — mall finns: `automations/whatsapp_assist.yaml.example`
4. **Vitlistat telefonnummer** i `secrets.yaml`

## Rekommenderad ordning

1. Sätt `HA_TOKEN` i `.env` (skript: `scripts/oppna-ha-token.ps1`)
2. Kör `.\scripts\ha-inventory.ps1` för exakt lista över integrationer och add-ons
3. Installera WhatsApp-brygga (se `docs/whatsapp-chatt-plan.md`)
4. Deploya automation från `automations/whatsapp_assist.yaml.example`

## Säkerhet (viktigt — publikt repo)

`configuration.yaml` innehöll **Join API-nycklar i klartext**. Dessa har flyttats till `!secret` i en uppdatering.
**Byt/regenerera Join API-nycklar** i Join-appen om de legat publikt länge.

Gamla lösenord i kommenterade rader i yaml (netgear, spotify m.m.) finns kvar i **git-historik** — rotera om de varit riktiga.
