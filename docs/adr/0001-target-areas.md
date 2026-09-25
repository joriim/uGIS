# 0001 — Target areas selected by peltolohkotunnus or kiinteistötunnus

Status: proposed, 2026-09-25

## Context

The Farm Pack was specified for one farm, selected by Ruokavirasto field parcel ids or a drawn boundary. Users also want packs and later products for forests and other land: meadows and wetlands, brownfields, and urban green areas such as parks. Those areas are not in the field parcel register, but nearly all land in Finland belongs to a registered property with a kiinteistötunnus.

## Decision

1. A **target area** is a named, saved area made of **parts**. Each part is one of:
   - a field parcel, selected by **peltolohkotunnus** (10 digits), resolved from the Ruokavirasto parcel register (`ruokavirasto_peltolohkot`) for a chosen year, latest by default;
   - a property, selected by **kiinteistötunnus**, resolved from MML property boundaries (`mml_kiinteistot`). A property can consist of several palstat (separate land parcels); all of them belong to the part.
   - Map taps (`pick_at`) select the field parcel or property under the point and are stored as that parcel or property, not as a point.
2. Each part has an **area class**: `field` (pelto), `forest` (metsä), `other_green` (muu viheralue), `brownfield` (ruskea alue), `urban_green` (kaupunkivihreä) or `unclassified`. Field parcels default to `field`, properties to `unclassified`. The user sets the class; it is not inferred in the MVP.
3. The area's geometry is the **union of its parts**. Geometry is stored in EPSG:4326 (interchange rule); areas in hectares are computed in EPSG:3067.
4. Tools: `select_target_area` (create, add, remove, replace parts), `list_target_areas`, `delete_target_area` (confirmed). `request_farm_pack` and `request_product` take `target_area_id`; a drawn `aoi` remains the fallback. The earlier `request_farm_pack.parcel_ids` is replaced by `target_area_id`.
5. A target area is a STAC item with `ufield:visibility` (default `proprietary`), and `ufield:provenance` that lists each part's id, source layer and register year. Products built from it record the target area id as an input.

## Consequences

- Lookup of ids needs the server: MML property data requires the API key, and one property lookup can return several palstat.
- A field parcel and the property it lies on can overlap. The union handles geometry; hectares per class are computed per part, so totals by class can exceed the area's total and the UI must show the union total.
- Only the id and boundary are fetched. Owner information is not open data and is never requested. A user can select any property, since the boundaries are public; the saved selection is still proprietary because it shows the user's interest in that land.
- Määräalat (unseparated parcels, `-M` suffix) have no open boundary and are rejected with a clear error.
- Peltolohkotunnus can change between register years when parcels are split or merged; a part records its year, and re-resolving to a newer year is an explicit user action.
- The Farm Pack name stays for now, although packs can cover forest and urban land. Revisit the name before the store listing.

## Open questions

- Exact MML collection id and attribute for kiinteistötunnus, and Ruokavirasto's attribute for peltolohkotunnus (TODOs in `config/layers.yaml`).
- Whether to suggest an area class from land cover (Maastotietokanta, CORINE) after the MVP.
