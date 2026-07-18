# Cursor-chattar — Home Assistant

Datum: 2026-07-19  
Migrering genomförd i chatt `e6a8ce31`.

## Bakgrund

Home Assistant-chattar låg kvar i workspace **granskningsverktyget** (`C:\kod\granskningsverktyget\sessionversion`) efter att HA-projektet flyttats till eget repo (`C:\kod\home_assistant`). Totalt sju chattar har flyttats till rätt workspace.

## Flyttade chattar (7)

| Chatt-ID | Titel |
|----------|-------|
| `43d92d09-ef46-49d1-996b-cbb1a0969eff` | Home assistant ärende |
| `6f95005f-5c43-4446-abcd-bb258a38e637` | Home Assistant curtain issue |
| `8d1767e5-4fcb-404a-8cf1-d6cf6a502aa1` | HA: Rullgardin sovrummet |
| `187d3ed9-f6da-4f0a-9088-30452af78cce` | Ha: Badrummet tempsensorer |
| `66116a8d-4934-47cc-a94c-745cfe2455b7` | Question notification rule |
| `cbb72da0-39d4-47de-ae58-580b4bb246b6` | Stabilisera Nabu-notiser |
| `eaad5093-52d6-4ac5-bcfe-6ff93381858d` | HA: Badrumsbelysning + dusch |

De två sista flyttades som **aktiva** chattar (`isArchived=0`).

## Efter migrering

**Ladda om Cursor** så att chattlistan uppdateras:

1. **Ctrl+Shift+P**
2. Välj **Developer: Reload Window**

Därefter ska alla flyttade chattar synas under home_assistant-projektet.

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
