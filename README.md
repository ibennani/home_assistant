# Home Assistant-projekt

Versionshantering och verktyg för Home Assistant. Mål: WhatsApp-chatt med Assist.

Repo: https://github.com/ibennani/home_assistant

**Publikt repo = kod syns för alla. Hemligheter (token, lösenord) ligger aldrig i git.**

Senaste lägesrapport: [docs/lage-rapport.md](docs/lage-rapport.md)

## Steg 1 — Öppna rätt mapp i Cursor

**File → Open Folder** → `C:\kod\home_assistant`

Starta en **ny chatt** i det workspace:t.

## Steg 2 — Konfigurera lokalt

```powershell
cd C:\kod\home_assistant
copy .env.example .env
notepad .env
```

Fyll i:
- `HA_URL` — t.ex. `http://192.168.x.x:8123` eller Nabu Casa-URL
- `HA_TOKEN` — long-lived token (Inställningar → Personer → din användare → Tokens)
- `HA_SSH_HOST` — t.ex. `homeassistant.local`
- `HA_ALLOWED_PHONE` — ditt nummer utan +, t.ex. `46701234567`

## Steg 3 — Git och GitHub

```powershell
cd C:\kod\home_assistant
git init -b main
git remote add origin https://github.com/ibennani/home_assistant.git
git add -A
git commit -m "Lägg till: Grundstruktur för Home Assistant-projekt"
git push -u origin main
```

Om repot redan har innehåll på GitHub:
```powershell
git pull origin main --rebase
git push -u origin main
```

Gör repot **Public** på GitHub (Settings → General → Change visibility) om molnläget ska kunna läsa det.

## Steg 4 — Inventera HA

Med Git Bash eller WSL:
```bash
./scripts/ha-inventory.sh
```

Eller med PowerShell:
```powershell
.\scripts\ha-inventory.ps1
```

Rapporten sparas i `reports\` (gitignorerad).

## Steg 5 — SSH-test

```powershell
ssh root@homeassistant.local
# eller
bash scripts/ssh-ha.sh ha core info
```

## Projektstruktur

```
home_assistant/
├── automations/       # YAML-automatiseringar
├── docs/              # Dokumentation
├── scripts/           # Inventering, SSH, säkerhetskontroll
├── .env.example       # Mall (kopiera till .env)
└── reports/           # Lokala rapporter (ej i git)
```

## Säkerhet

Se [docs/sakerhet.md](docs/sakerhet.md).

**Viktigt:** `secrets.yaml` ligger kvar lokalt men trackas inte i git. Filen fanns i ett tidigare commit på GitHub — byt lösenord/nycklar om repot blir publikt.

## Befintlig HA-config

Repot innehåller din befintliga YAML-config i rotmappen (`configuration.yaml`, `automations.yaml` m.m.). Nya mallar och verktyg ligger under `automations/`, `scripts/` och `docs/`.

## Cursor MCP

Koppla Cursor till Home Assistant via ha-mcp — se [docs/ha-mcp.md](docs/ha-mcp.md).

Kopiera `.cursor/mcp.json.example` till `.cursor/mcp.json` och klistra in **Nabu Casa-webhook-URL** från proxy-add-onens logg (eller lokal URL om du bara kör Agent-chatt hemma).

**Cursor Automations** (t.ex. `cursor+ha test`) kräver dessutom MCP i [cursor.com → Settings → MCP](https://cursor.com/settings) — lokal `mcp.json` räcker inte. Se felsökning i [docs/ha-mcp.md](docs/ha-mcp.md#5b-felsökning--cursor-automation--agenten-cursorha-test-når-inte-ha).

## WhatsApp-chatt

Se [docs/whatsapp-chatt-plan.md](docs/whatsapp-chatt-plan.md).
