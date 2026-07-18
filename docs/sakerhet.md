# Säkerhet i publikt repo

## Kort svar

**Publikt repo** = kod och mallar syns. **Ingen** kan styra ditt hem utan `HA_TOKEN`, SSH-nyckel och nätverksåtkomst.

## Committa ALDRIG

| Fil | Innehåll |
|-----|----------|
| `.env` | API-token |
| `secrets.yaml` | Lösenord på HA-servern |
| `.storage/`, `*.db` | Intern HA-data |
| `reports/` | Inventering med enhetsnamn |

## Var hemligheter ska ligga

- **Din dator:** `C:\kod\home_assistant\.env` (kopiera från `.env.example`)
- **HA-servern:** `/config/secrets.yaml`

## Skapa API-token

1. Home Assistant → Inställningar → Personer
2. Din användare → Long-Lived Access Tokens → Skapa
3. Klistra in i `.env` som `HA_TOKEN=...`

## Före varje commit

```powershell
bash scripts/pre-commit-check.sh
```

## För Cursor Cloud Agent

- Repot måste vara **public** på GitHub
- Token ska **inte** ligga i repot
- SSH till HA fungerar bara från **lokal** Cursor (din dator), inte molnet
