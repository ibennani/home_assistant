# Marginal elpris (kWh-kostnad i hemmet)

## Syfte

All **kostnadsberäkning** i projektet (tvätt, disk, schemaläggning, notiser, grafer, sammandrag) ska visa **faktiskt kr/kWh** — det Tibber anger per kvart (inkl. skatter enligt Tibbers API), inte bara Nord Pool spot.

## Källsensorer

| Entitet | Användning |
|---------|------------|
| `sensor.elpris_marginal_kwh_se3` | **Standard** för allt UI och kostnad (`today`/`tomorrow`, `raw_*`) |
| `sensor.elpris_faktisk_kwh_se3` | Fylls av `scripts/elpris-synka-tibber-faktiska.py` via `tibber.get_prices` |
| `sensor.nordpool_kwh_se3_sek_3_10_025` | Endast jämförelse (börs) i dashboard |
| `sensor.electricity_price_eksharadsgatan_6` | Tibber «nu» (elhandel); används i fallback |

### Attribut på marginal-sensorn

- **state** — kr/kWh nu (från Tibber-synk eller fallback)
- **price_source** — `tibber` eller `fallback`
- **today** / **tomorrow** — 96 kvartar med faktiskt/marginalpris
- **raw_today** / **raw_tomorrow** — `{start, end, value}` för exakt kostnad
- **synced_at** — senaste Tibber-synk

## Synk

- **Skript:** `script.elpris_synka_tibber_faktiska_priser` / `shell_command.elpris_synka_tibber_faktiska`
- **Automation:** `elpris_synka_tibber_faktiska` — vid start, varje timme (:05), 13:35 och 14:05
- Körs också efter `script.git_synka_config`

## Fallback

Om Tibber-synk saknas: Nord Pool per kvart + energiskatt + Ellevio + (Tibber elhandel − spot nu), annars fast Tibber-påslag-helper.

Helpers (`input_number.elpris_*_ore`) används **inte** när `price_source` är `tibber`.

## Regler

1. Använd **aldrig** rå Nord Pool för kr-beräkningar i nya automationer.
2. För kostnad: `sensor.elpris_marginal_kwh_se3` eller `raw_today`/`raw_tomorrow` på samma sensor.
3. Börs visas separat i UI om användaren ska jämföra spot.

## Verifiering

```bash
bash scripts/verify-change.sh
python3 scripts/check-elpris-source.py
```

Live: `state_attr('sensor.elpris_marginal_kwh_se3','price_source')` ska vara `tibber` efter synk; jämför «nu» med Tibber-appen.
