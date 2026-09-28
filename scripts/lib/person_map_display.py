"""En källa för personmarkörer på kartor: initialer (label) och förnamn (tooltip).

Dashboard: scripts/sync-dashboard-person-maps.py
Template: generate-ilias-zone-automation.py (spionkarta-sensorer)
Kontroll: scripts/check-person-map-display.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonMapDisplay:
    slug: str
    first_name: str
    initials: str
    map_card_title: str | None = None
    map_entity: str | None = None
    spion_template: bool = True

    @property
    def entity_for_map(self) -> str:
        return self.map_entity or f"sensor.{self.slug}_spionkarta"

    @property
    def title(self) -> str:
        base = self.map_card_title or self.first_name
        return f"{base} senaste 24 timmarna"


# Ordning = ordning på Spion-flikens kartor i dashboarden.
PERSON_MAP_DISPLAYS: tuple[PersonMapDisplay, ...] = (
    PersonMapDisplay("ilias", "Ilias", "IB"),
    PersonMapDisplay("anna", "Anna", "AB"),
    PersonMapDisplay(
        "isabelle",
        "Asher",
        "AS",
        map_card_title="Asher",
        map_entity="sensor.asher",
        spion_template=False,
    ),
    PersonMapDisplay("erik", "Erik", "EB"),
)

SPION_GPS_TRACKERS: dict[str, str] = {
    "anna": "device_tracker.anna_s22_ultra",
    "erik": "device_tracker.erik_s23",
    "ilias": "device_tracker.ilias_s23_ultra",
    "isabelle": "person.isabelle_sovig",
}

MAP_PERSON_BEGIN = "# BEGIN map-person (scripts/sync-dashboard-person-maps.py)"
MAP_PERSON_END = "# END map-person"
