# Marginal elpris (kWh-kostnad i hemmet)

## Syfte

All **kostnadsberäkning** i projektet (tvätt, disk, schemaläggning, notiser) ska använda samma källa: vad det **faktiskt kostar** att förbruka en kWh just nu och per tidslucka — inte bara Nord Pool spot.

## Källsensor

| Entitet | Användning |
|---------|------------|
| `sensor.elpris_marginal_kwh_se3` | **Standard** för kostnad, `today`/`tomorrow`, `raw_today`/`raw_tomorrow` |
| `sensor.nordpool_kwh_se3_sek_3_10_025` | Endast börs/spot (dashboard, jämförelse) |
| `sensor.electricity_price_eksharadsgatan_6` | Tibber elhandel (ingår i marginalpris «nu») |

### Attribut på marginal-sensorn

- **state** — marginal kr/kWh nu (Tibber elhandel + energiskatt + nät, eller spot + helpers som fallback)
- **today** / **tomorrow** — timlistor med marginal kr/kWh
- **raw_today** / **raw_tomorrow** — kvartslistor `{start, end, value}` för exakt kostnad under pågående förbrukning
- **spot_kwh**, **elhandel_kwh** — referensvärden

## Justerbara helpers (`input_number`)

- `elpris_energiskatt_ore` — energiskatt inkl. moms (öre/kWh)
- `elpris_ellevio_overforing_ore` — Ellevio överföring inkl. moms
- `elpris_tibber_paslag_ore` — Tibber-påslag på kvartsplan när Tibber-sensor saknas (fallback för historik/slotar)

Kalibrera helpers om Tibber-appen och HA skiljer sig mer än några öre.

## Regler för nya automationer och script

1. Använd **aldrig** rå Nord Pool för kr-beräkningar.
2. För «nu»: `states('sensor.elpris_marginal_kwh_se3')` eller slot-loop mot `raw_today`/`raw_tomorrow`.
3. För timmedel/snitt: `state_attr(..., 'today')` / `tomorrow` på samma sensor.
4. Visa börs separat i UI om användaren ska se spot — inte som underlag för kostnad.

## Implementering

Sensorn definieras i `includes/template.yaml` (`unique_id: elpris_marginal_kwh_se3`).

Efter ändring: `template.reload` (ingen full omstart).

## Verifiering

```bash
bash scripts/verify-change.sh
python3 scripts/check-elpris-source.py
```

Live: jämför `sensor.elpris_marginal_kwh_se3` med Tibber-appens «nu»-pris (ca samma öre/kWh).
