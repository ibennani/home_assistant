# Git-synk från Cursor Cloud

## Varför fungerar lokalt men inte i molnet?

| | **Cursor på din dator** | **Cursor Cloud** |
|---|---|---|
| Nätverk | Samma LAN som HA (`192.168.0.222`) | Cursor-servrar på internet |
| SSH | `ssh root@homeassistant.local` fungerar | Privata IP-adresser går inte att nå |
| HA API | Lokal URL eller Nabu Casa | **Nabu Casa webhook** (MCP) |

Molnet når alltså redan din HA via **MCP + Nabu Casa** — men inte SSH. Lösningen är att exponera `git pull` som en **Home Assistant-tjänst** som MCP kan anropa.

## Engångsinstallation på HA-servern

Efter att `shell_command.git_pull` och `script.git_synka_config` finns i repot, kör **en gång** i SSH/Web Terminal:

```bash
cd /config
git pull origin main
```

Ladda om YAML (Inställningar → YAML → **Alla YAML-konfigurationer**) eller starta om Home Assistant Core.

## Synka från Cursor Cloud (agent)

Agenten anropar via MCP:

```text
ha_call_service(domain="script", service="git_synka_config")
```

Det kör i ordning:

1. `git pull origin main` i `/config` (logg: `/config/git-pull.log`)
2. Laddar om core, automatiseringar och templates

Alternativ utan reload:

```text
ha_call_service(domain="shell_command", service="git_pull")
```

## Synka från din dator

Som tidigare:

```bash
bash scripts/ssh-ha.sh 'cd /config && git pull origin main'
```

eller kör skriptet **Git: Synka /config från GitHub** i HA UI.

## Säkerhet

- Endast den som har **MCP-webhook-URL** (eller HA admin-token) kan trigga synken.
- Committa aldrig webhook-URL eller tokens till git.
- Vid merge-konflikt på servern misslyckas `git pull` — löses manuellt i SSH-terminalen.
