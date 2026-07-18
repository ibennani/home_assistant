# Plan: WhatsApp-chatt med Home Assistant

## Arkitektur

```
WhatsApp → WhatsApp-brygga (add-on) → Automation → conversation.process → svar
```

## 1. Inventera

```powershell
.\scripts\ha-inventory.ps1
```

Kolla i rapporten:
- Finns `whatsapp` bland components?
- Vilka `conversation.*`-agenter finns?
- Vilka add-ons är installerade?

## 2. WhatsApp-brygga (om saknas)

Rekommenderat: [FaserF/ha-whatsapp](https://github.com/FaserF/ha-whatsapp)

1. Installera add-on
2. Installera integration via HACS
3. Para med QR-kod (helst sekundärt WhatsApp-nummer)

## 3. Conversation-agent

Inställningar → Assisterare → Språkmodeller (inbyggd, OpenAI, Gemini, Ollama).

## 4. Automation

Mall: `automations/whatsapp_assist.yaml.example`

Sätt `whatsapp_allowed_number` i HA:s `secrets.yaml`.

## 5. Säkerhet

Vitlista endast ditt telefonnummer i automationen.
