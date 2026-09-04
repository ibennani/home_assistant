/**
 * Zonkarta: leaflet-draw i strict mode (ES-moduler) kraschar utan deklarerad
 * radius i Edit.Circle._resize. Utan patchen kan circle.editing.enable() misslyckas
 * och inga cirklar visas i Inställningar → Zoner.
 *
 * Laddas globalt via frontend.extra_module_url (före HA:s leaflet-draw).
 */
globalThis.radius = undefined;
