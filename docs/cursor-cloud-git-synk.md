# Git-synk från Cursor Cloud

## Varför fungerar lokalt men inte i molnet?

| | **Cursor på din dator** | **Cursor Cloud** |
|---|---|---|
| Nätverk | Samma LAN som HA (`192.168.0.222`) | Cursor-servrar på internet |
| SSH | `ssh root@homeassistant.local` fungerar | Privata IP-adresser går inte att nå |
| HA API | Lokal URL eller Nabu Casa | **Nabu Casa webhook** (MCP) |

Molnet når din HA via **MCP + Nabu Casa**. Git-synk sker via tjänster i HA — inte SSH.

## Komponenter (i repot)

| Komponent | Syfte |
|-----------|--------|
| `shell_command.git_pull` | `git fetch` + `reset --hard origin/main` i `/config` |
| `script.git_synka_config` | Pull + reload core/automations/templates |
| `automation` **System: Git-synk från GitHub** | Triggas av event `cursor_git_synk` |

Logg: `/config/git-pull.log` (gitignorerad via `*.log`).

**OBS:** `reset --hard` gör att ocommittade YAML-ändringar på servern skrivs över av GitHub `main`. Det är avsiktligt — repot är källan till sanning.

## Cursor Cloud-agent (standardflöde)

Efter commit/push till `main`:

```text
ha_call_write_tool(
  name="ha_call_event",
  arguments={"event_type": "cursor_git_synk"}
)
```

Alternativ:

```text
ha_call_write_tool(
  name="ha_call_service",
  arguments={
    "domain": "script",
    "service": "git_synka_config",
    "entity_id": "script.git_synka_config"
  }
)
```

Därefter: verifiera med `ha_get_system_health(include="config_check")`.

## Dashboard (Översikt)

Dashboarden `dashboard-september-2025` versioneras i git som `dashboards/dashboard-september-2025.yaml` och registreras i `includes/lovelace.yaml`.

Efter ändringar i dashboard-YAML: samma git-synk som ovan, sedan ladda om sidan i webbläsaren (hård refresh om kort inte uppdateras).

Exportera aktuell live-kopia från HA till repot:

```bash
python3 scripts/export-dashboard-from-ha.py
```

## Manuellt i HA UI

Kör skriptet **Git: Synka /config från GitHub** eller tryck på knappen om du lagt till en i dashboard.

## Från din dator (SSH)

```bash
bash scripts/ssh-ha.sh 'cd /config && git fetch origin main && git reset --hard origin/main'
```

## Säkerhet

- Kräver MCP-webhook-URL eller HA admin-token.
- Committa aldrig webhook-URL eller tokens till git.
