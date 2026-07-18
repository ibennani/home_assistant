# Cursor-chattar — Home Assistant

Datum: 2026-07-19  
Migrering genomförd i chatt `e6a8ce31`.

## Bakgrund

Arkiverade Home Assistant-chattar låg kvar i workspace **granskningsverktyget** (`C:\kod\granskningsverktyget\sessionversion`) efter att HA-projektet flyttats till eget repo (`C:\kod\home_assistant`). Fem arkiverade chattar har flyttats till rätt workspace och behållit arkiverad status.

## Flyttade chattar (5)

| Chatt-ID | Titel |
|----------|-------|
| `43d92d09-ef46-49d1-996b-cbb1a0969eff` | Home assistant ärende |
| `6f95005f-5c43-4446-abcd-bb258a38e637` | Home Assistant curtain issue |
| `8d1767e5-4fcb-404a-8cf1-d6cf6a502aa1` | HA: Rullgardin sovrummet |
| `187d3ed9-f6da-4f0a-9088-30452af78cce` | Ha: Badrummet tempsensorer |
| `66116a8d-4934-47cc-a94c-745cfe2455b7` | Question notification rule |

## Efter migrering

**Ladda om Cursor** så att chattlistan uppdateras:

1. **Ctrl+Shift+P**
2. Välj **Developer: Reload Window**

Därefter ska de arkiverade chattarna synas under home_assistant-projektet.

## Kvar i granskningsverktyget (2, ej arkiverade)

Dessa flyttades inte (aktiva chattar i fel workspace):

- Stabilisera Nabu-notiser
- HA: Badrumsbelysning + dusch

## Var Cursor lagrar chattar (Windows)

| Plats | Innehåll |
|-------|----------|
| `%APPDATA%\Cursor\User\globalStorage\state.vscdb` | Metadata (`composerHeaders`) och konversationsdata (`cursorDiskKV`) |
| `%USERPROFILE%\.cursor\projects\c-kod-home-assistant\agent-transcripts\` | Agent-transcripts per chatt |

## Återställning (rollback)

Backup av databasrader före migrering:

```
C:\kod\home_assistant\scripts\_ha_chat_migration_backup.json
```

Filen är **gitignorerad** (innehåller full chattdata). Behåll den lokalt tills du verifierat att migreringen fungerar.

Migreringsskript (kan köras om igen vid behov, t.ex. efter manuell återställning från backup):

```
scripts/migrate_ha_chats.py
```
