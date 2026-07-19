import tarfile
from pathlib import Path
BACKUP = Path("/backup/3f04bae7.tar")
WORK = Path("/tmp/ha-recovery/3f04bae7")
WORK.mkdir(parents=True, exist_ok=True)
print("extracting outer...")
with tarfile.open(BACKUP, "r:") as outer:
    outer.extract("homeassistant.tar.gz", WORK)
inner = WORK / "homeassistant.tar.gz"
print("inner size", inner.stat().st_size)
targets = {
    "automations.yaml": WORK / "automations.yaml",
    "configuration.yaml": WORK / "configuration.yaml",
    "scripts.yaml": WORK / "scripts.yaml",
    "ui-lovelace.yaml": WORK / "ui-lovelace.yaml",
    "groups.yaml": WORK / "groups.yaml",
    "zone.yaml": WORK / "zone.yaml",
    "scenes.yaml": WORK / "scenes.yaml",
    "known_devices.yaml": WORK / "known_devices.yaml",
}
input_files = ["input_boolean.yaml", "input_datetime.yaml", "input_number.yaml", "input_select.yaml", "input_text.yaml"]
with tarfile.open(inner, "r:gz") as t:
    members = {m.name: m for m in t.getmembers()}
    for base, dest in targets.items():
        key = f"data/{base}"
        if key in members:
            t.extract(key, WORK)
            (WORK / key).rename(dest)
            print("ok", base)
        else:
            print("MISSING", key)
    for inf in input_files:
        key = f"data/{inf}"
        if key in members:
            t.extract(key, WORK)
            (WORK / key).rename(WORK / inf)
            print("ok", inf)
auto = WORK / "automations.yaml"
if auto.exists():
    text = auto.read_text(errors="replace")
    idx = text.find("Huset: Styr house_time_modes")
    print("=== house_time_modes ===")
    print(text[idx:idx+900] if idx >= 0 else "NOT FOUND")
print("DONE", WORK)
